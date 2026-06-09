"""
app/mcp/mongodb/client.py

MongoDB MCP client — singleton connection used by all memory services.

Connection modes (in priority order):
  1. MONGODB_MCP_URL   — MCP server URL (future: tool-calling via Anthropic SDK)
  2. MONGODB_URI       — Direct pymongo connection (current Phase 1 implementation)

Phase 1 uses direct pymongo. The MCP URL path is wired and ready for Phase 2
activation without any code changes in the memory services.

Add to .env:
    MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/
    MONGODB_DB_NAME=ai_content_studio
    MONGODB_MCP_URL=   # leave empty for Phase 1
"""
import os
import sys
import logging
from typing import Optional

log = logging.getLogger(__name__)
_MODULE = sys.modules[__name__]


def is_mongodb_enabled() -> bool:
    """True when MongoDB is configured (either MCP URL or direct URI)."""
    return bool(
        os.getenv("MONGODB_URI", "").strip() or
        os.getenv("MONGODB_MCP_URL", "").strip()
    )


def get_mongodb_client():
    """
    Return the singleton MongoDB client.
    Returns None if not configured — callers handle None gracefully.
    Initializes on first call.
    """
    if hasattr(_MODULE, "_client"):
        return _MODULE._client

    mcp_url = os.getenv("MONGODB_MCP_URL", "").strip()
    direct_uri = os.getenv("MONGODB_URI", "").strip()

    if mcp_url:
        # Phase 2 path: MCP tool-calling
        # When activated, agents call MongoDB through the Anthropic MCP SDK
        # instead of pymongo directly. The memory services need no changes.
        log.info(
            f"[mongodb] MONGODB_MCP_URL detected ({mcp_url[:40]}...) — "
            "MCP tool-calling path will be activated in Phase 2"
        )
        if direct_uri:
            log.info("[mongodb] MONGODB_URI also set — using direct connection for Phase 1")
        # Fall through to direct connection if URI also available

    if not direct_uri:
        log.warning(
            "[mongodb] Neither MONGODB_URI nor MONGODB_MCP_URL set. "
            "Creator memory is disabled — add MONGODB_URI to .env to enable."
        )
        _MODULE._client = None
        _MODULE._db = None
        return None

    return _init_direct_connection(direct_uri)


def get_mongodb_db():
    """Return the MongoDB database object. None if not connected."""
    if not hasattr(_MODULE, "_db"):
        get_mongodb_client()
    return getattr(_MODULE, "_db", None)


def _init_direct_connection(uri: str):
    """Open a direct pymongo connection and verify it with ping."""
    db_name = os.getenv("MONGODB_DB_NAME", "ai_content_studio").strip()

    try:
        from pymongo import MongoClient
        from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

        client = MongoClient(
            uri,
            serverSelectionTimeoutMS=4000,
            connectTimeoutMS=4000,
            socketTimeoutMS=10000,
        )

        # Verify connection is live
        client.admin.command("ping")

        db = client[db_name]
        _MODULE._client = client
        _MODULE._db = db

        _ensure_indexes(db)

        print(f"[mongodb] Connected — database: '{db_name}'")
        log.info(f"[mongodb] Connected — database: '{db_name}'")
        return client

    except ImportError:
        log.warning(
            "[mongodb] pymongo not installed. Run: pip install pymongo\n"
            "Creator memory disabled."
        )
        _MODULE._client = None
        _MODULE._db = None
        return None

    except Exception as e:
        log.warning(
            f"[mongodb] Connection failed: {e}\n"
            "Creator memory disabled — workflow continues with PostgreSQL only."
        )
        _MODULE._client = None
        _MODULE._db = None
        return None


def _ensure_indexes(db) -> None:
    """Create required indexes on first connection."""
    try:
        # creator_memory: one document per user
        db.creator_memory.create_index("user_id", unique=True, background=True)
        db.creator_memory.create_index("channel_id", background=True)

        # research_sessions: many per user, newest first
        db.research_sessions.create_index(
            [("user_id", 1), ("created_at", -1)], background=True
        )
        db.research_sessions.create_index("topic", background=True)
        db.research_sessions.create_index("generation_id", background=True)

        # content_pieces: one per completed generation
        db.content_pieces.create_index(
            "generation_id", unique=True, background=True
        )
        db.content_pieces.create_index(
            [("user_id", 1), ("created_at", -1)], background=True
        )

        log.info("[mongodb] Indexes created/verified")

    except Exception as e:
        log.warning(f"[mongodb] Index setup warning (non-fatal): {e}")
