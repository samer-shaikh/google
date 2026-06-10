"""
app/mcp/mongodb/mcp_runner.py

Thin async wrapper around the official MongoDB MCP server (stdio transport).
Spawns `npx mongodb-mcp-server@latest` as a subprocess and sends
JSON-RPC 2.0 tool calls over stdin/stdout.

Used ONLY by research_agent and video_idea_agent for read-only queries.
All writes continue through PyMongo (tools.py) — zero disruption.

Lifecycle:
  - Server is spawned lazily on first call inside the running event loop.
  - Singleton subprocess reused across all calls.
  - Lock is created lazily (avoids cross-loop issues at import time).
  - If spawn or call fails for any reason, returns None silently.
    Callers must handle None — agents fall back to existing behaviour.
"""

import os
import json
import asyncio
import logging
import shutil
from pathlib import Path
from typing import Optional, Any

from dotenv import load_dotenv

load_dotenv()

CONFIG_PATH = Path(__file__).parent / "mongodb_mcp.json"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    config = json.load(f)

config["MONGODB_URI"] = os.getenv("MONGODB_URI")


log = logging.getLogger(__name__)

# Module-level singleton state
_process: Optional[asyncio.subprocess.Process] = None
_lock: Optional[asyncio.Lock] = None          # created lazily inside event loop
_request_id = 0
_initialized = False
_db_name = os.getenv("MONGODB_DB_NAME", "ai_content_studio")


def _get_lock() -> asyncio.Lock:
    """Return (or create) the asyncio Lock — always inside the running loop."""
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def _load_config() -> dict:
    """Load mongodb_mcp.json and return the mongodb server config block."""
    config_path = Path(__file__).parent / "mongodb_mcp.json"
    if not config_path.exists():
        raise FileNotFoundError(f"MongoDB MCP config not found: {config_path}")
    raw = json.loads(config_path.read_text())
    # Support both flat format and nested mcpServers format
    if "mcpServers" in raw and "mongodb" in raw["mcpServers"]:
        return raw["mcpServers"]["mongodb"]
    return raw


def _build_env(config: dict) -> dict:
    """Merge OS env with config env block (connection string lives in json)."""
    env = dict(os.environ)
    env.update(config.get("env", {}))
    return env


async def _get_process() -> Optional[asyncio.subprocess.Process]:
    """Return (or spawn) the singleton MCP subprocess."""
    global _process, _initialized

    if _process is not None and _process.returncode is None:
        return _process  # already running fine

    try:
        config = _load_config()
        env = _build_env(config)
        command = config.get("command", "npx")
        args = config.get("args", ["-y", "mongodb-mcp-server@latest"])

        # On Windows, resolve the full path to npx/node executable
        # to avoid WinError 2 (file not found) with subprocess
        resolved_command = shutil.which(command)
        if resolved_command is None:
            # Try common Windows Node.js locations
            for candidate in [
                r"C:\Program Files\nodejs\npx.CMD",
                r"C:\Program Files\nodejs\npx.cmd",
                r"C:\Program Files (x86)\nodejs\npx.CMD",
                os.path.expanduser(r"~\AppData\Roaming\npm\npx.CMD"),
            ]:
                if os.path.exists(candidate):
                    resolved_command = candidate
                    break

        if resolved_command is None:
            raise FileNotFoundError(
                f"'{command}' not found in PATH. "
                "Install Node.js from https://nodejs.org"
            )

        log.info(f"[mcp_runner] Spawning: {resolved_command} {' '.join(args)}")

        _process = await asyncio.create_subprocess_exec(
            resolved_command,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        # Give the process a moment to start up before the handshake
        await asyncio.sleep(1.5)

        # JSON-RPC 2.0 initialize handshake
        await _send_raw({
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "ai-content-studio", "version": "1.0.0"},
            },
        })

        init_resp = await _read_response(timeout=15.0)

        if init_resp and "result" in init_resp:
            # Send initialized notification (required by MCP spec)
            await _send_raw({
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            })
            _initialized = True
            print("[mcp_runner] ✅ MongoDB MCP server initialized successfully")
            log.info("[mcp_runner] MongoDB MCP server initialized successfully")
        else:
            log.warning(f"[mcp_runner] Unexpected init response: {init_resp}")
            _initialized = False

        return _process

    except FileNotFoundError as e:
        log.warning(f"[mcp_runner] Config missing: {e}")
        return None
    except Exception as e:
        log.debug(f"[mcp_runner] Failed to spawn MCP server: {e}")
        _process = None
        _initialized = False
        return None


async def _send_raw(payload: dict) -> None:
    """Write a JSON-RPC message to the subprocess stdin."""
    if _process is None or _process.stdin is None:
        return
    try:
        line = json.dumps(payload) + "\n"
        _process.stdin.write(line.encode())
        await _process.stdin.drain()
    except Exception as e:
        log.warning(f"[mcp_runner] Write error: {e}")


async def _read_response(timeout: float = 10.0) -> Optional[dict]:
    """Read one JSON-RPC response line from subprocess stdout."""
    if _process is None or _process.stdout is None:
        return None
    try:
        line = await asyncio.wait_for(_process.stdout.readline(), timeout=timeout)
        if not line:
            return None
        text = line.decode().strip()
        if not text:
            return None
        return json.loads(text)
    except asyncio.TimeoutError:
        log.warning("[mcp_runner] Timeout waiting for MCP response")
        return None
    except json.JSONDecodeError as e:
        log.warning(f"[mcp_runner] JSON decode error: {e}")
        return None
    except Exception as e:
        log.warning(f"[mcp_runner] Read error: {e}")
        return None


async def call_mcp_tool(tool_name: str, arguments: dict) -> Optional[Any]:
    """
    Call a MongoDB MCP tool and return the parsed result.

    Args:
        tool_name:  MCP tool name e.g. "find", "aggregate", "count"
        arguments:  Tool arguments dict (collection, filter, limit, etc.)
                    'database' is auto-injected from MONGODB_DB_NAME if missing.

    Returns:
        Parsed result (list/dict/str) on success, None on any failure.
        Always safe — never raises, never blocks the workflow.
    """
    global _request_id

    # Auto-inject database name
    if "database" not in arguments:
        arguments = {"database": _db_name, **arguments}

    async with _get_lock():
        proc = await _get_process()
        if proc is None or not _initialized:
            return None

        _request_id += 1
        req_id = _request_id

    try:
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }
        await _send_raw(payload)
        response = await _read_response()

        if response is None:
            return None

        if "error" in response:
            log.warning(f"[mcp_runner] Tool '{tool_name}' error: {response['error']}")
            return None

        result = response.get("result", {})
        # MCP spec: content is a list of typed blocks; text blocks carry JSON
        content = result.get("content", [])
        if content and isinstance(content, list):
            text = content[0].get("text", "")
            try:
                return json.loads(text)
            except Exception:
                return text if text else None

        return result if result else None

    except Exception as e:
        log.warning(f"[mcp_runner] call_mcp_tool('{tool_name}') failed: {e}")
        return None


async def shutdown_mcp() -> None:
    """Gracefully terminate the MCP subprocess. Called by FastAPI lifespan."""
    global _process, _initialized, _lock
    if _process and _process.returncode is None:
        try:
            _process.terminate()
            await asyncio.wait_for(_process.wait(), timeout=5.0)
            log.info("[mcp_runner] MongoDB MCP server stopped")
        except Exception as e:
            log.warning(f"[mcp_runner] Shutdown error: {e}")
    _process = None
    _initialized = False
    _lock = None  # reset so next startup creates a fresh lock in the new loop
