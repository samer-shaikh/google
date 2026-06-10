"""
app/mcp/elastic/mcp_runner.py

Async wrapper around the official Elasticsearch MCP server (stdio transport).
Mirrors the MongoDB mcp_runner pattern exactly.

Activation: set ELASTIC_MCP_URL in .env to enable, OR have ELASTICSEARCH_URL
set for direct elasticsearch-py usage via tools.py.

The MCP runner is used when you want the official @elastic/mcp-server-elasticsearch
running as a subprocess (tool-calling via JSON-RPC over stdio).

Usage:
    from app.mcp.elastic.mcp_runner import call_elastic_tool
    result = await call_elastic_tool("search", {
        "index": "trending_topics",
        "query": {"match": {"niche": "Python"}}
    })
"""

import os
import json
import asyncio
import logging
from pathlib import Path
from typing import Optional, Any

log = logging.getLogger(__name__)

_process: Optional[asyncio.subprocess.Process] = None
_lock: Optional[asyncio.Lock] = None
_request_id = 0
_initialized = False
_mcp_enabled = bool(os.getenv("ELASTIC_MCP_URL", "").strip())


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def _build_env() -> dict:
    env = dict(os.environ)
    es_url = os.getenv("ELASTICSEARCH_URL", "").strip()
    api_key = os.getenv("ELASTICSEARCH_API_KEY", "").strip()
    if es_url:
        env["ELASTICSEARCH_URL"] = es_url
    if api_key:
        env["ELASTICSEARCH_API_KEY"] = api_key
    return env


async def _get_process() -> Optional[asyncio.subprocess.Process]:
    global _process, _initialized

    if not _mcp_enabled:
        return None

    if _process is not None and _process.returncode is None:
        return _process

    try:
        env = _build_env()
        command = "npx"
        args = ["-y", "@elastic/mcp-server-elasticsearch@latest"]

        log.info(f"[elastic_mcp] Spawning: {command} {' '.join(args)}")

        _process = await asyncio.create_subprocess_exec(
            command, *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        await asyncio.sleep(2.0)

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
            await _send_raw({"jsonrpc": "2.0", "method": "notifications/initialized"})
            _initialized = True
            print("[elastic_mcp] ✅ Elasticsearch MCP server initialized successfully")
        else:
            log.warning(f"[elastic_mcp] Unexpected init response: {init_resp}")
            _initialized = False

        return _process

    except Exception as e:
        log.debug(f"[elastic_mcp] Failed to spawn: {e}")
        _process = None
        _initialized = False
        return None


async def _send_raw(payload: dict) -> None:
    if _process is None or _process.stdin is None:
        return
    try:
        _process.stdin.write((json.dumps(payload) + "\n").encode())
        await _process.stdin.drain()
    except Exception as e:
        log.warning(f"[elastic_mcp] Write error: {e}")


async def _read_response(timeout: float = 10.0) -> Optional[dict]:
    if _process is None or _process.stdout is None:
        return None
    try:
        line = await asyncio.wait_for(_process.stdout.readline(), timeout=timeout)
        if not line:
            return None
        text = line.decode().strip()
        return json.loads(text) if text else None
    except asyncio.TimeoutError:
        log.warning("[elastic_mcp] Timeout waiting for response")
        return None
    except Exception as e:
        log.warning(f"[elastic_mcp] Read error: {e}")
        return None


async def call_elastic_tool(tool_name: str, arguments: dict) -> Optional[Any]:
    """
    Call an Elasticsearch MCP tool. Returns None if MCP not enabled or on failure.
    Always safe to call — never raises.
    """
    global _request_id

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
            "params": {"name": tool_name, "arguments": arguments},
        }
        await _send_raw(payload)
        response = await _read_response()

        if response is None or "error" in response:
            if response:
                log.warning(f"[elastic_mcp] Tool '{tool_name}' error: {response['error']}")
            return None

        result = response.get("result", {})
        content = result.get("content", [])
        if content and isinstance(content, list):
            text = content[0].get("text", "")
            try:
                return json.loads(text)
            except Exception:
                return text if text else None
        return result if result else None

    except Exception as e:
        log.warning(f"[elastic_mcp] call_elastic_tool('{tool_name}') failed: {e}")
        return None


async def shutdown_elastic_mcp() -> None:
    """Gracefully terminate the Elastic MCP subprocess."""
    global _process, _initialized, _lock
    if _process and _process.returncode is None:
        try:
            _process.terminate()
            await asyncio.wait_for(_process.wait(), timeout=5.0)
            log.info("[elastic_mcp] Elasticsearch MCP server stopped")
        except Exception as e:
            log.warning(f"[elastic_mcp] Shutdown error: {e}")
    _process = None
    _initialized = False
    _lock = None
