"""
app/memory/mongo_client.py

MongoDB connection singleton for the memory layer.

Supports two connection modes:
  1. Direct MongoDB URI (MONGODB_URI in .env) — standard pymongo connection
  2. MongoDB MCP URL (MONGODB_MCP_URL in .env) — future MCP tool-calling integration

Phase 1 uses direct pymongo connection. The MCP integration path is
wired in but not active — it will be activated in Phase 2.

If neither env var is set, all memory operations become no-ops.
The workflow continues using PostgreSQL data only — nothing breaks.

Add to .env:
    MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/ai_content_studio
    MONGODB_DB_NAME=ai_content_studio          # optional, defaults to ai_content_studio
    MONGODB_MCP_URL=                            # leave empty for Phase 1
"""
import os
import sys
import logging

log = logging.getLogger(__name__)

_MODULE = sys.modules[__name__]


def is_memory_enabled() -> bool:
    """Returns True if MongoDB is configured."""
    return bool(
        os.getenv("MONGODB_URI", "").strip() or
        os.getenv("MONGODB_MCP_URL", "").strip()
    )


def get_mongo_client():
    """
    Return the singleton MongoDB client (pymongo MongoClient).
    Returns None if MongoDB is not configured — callers must handle None.
    """
    if hasattr(_MODULE, "_mongo_client"):
        return _MODULE._mongo_client

    uri = os.getenv("MONGODB_URI", "").strip()
    mcp_url = os.getenv("MONGODB_MCP_URL", "").strip()
    db_name = os.getenv("MONGODB_DB_NAME", "ai_content_studio").strip()

    if mcp_url:
        # Phase 2: MCP tool-calling path
        # For now, log and fall through to direct connection if URI also set
        log.info("[memory] MONGODB_MCP_URL detected — MCP path will be activated in Phase 2")

    if not uri:
        log.warning(
            "[memory] MONGODB_URI not set — memory layer disabled. "
            "Workflow continues with PostgreSQL data only. "
            "Add MONGODB_URI to .env to enable persistent creator memory."
        )
        _MODULE._mongo_client = None
        _MODULE._mongo_db = None
        return None

    try:
        from pymongo import MongoClient
        from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

        client = MongoClient(
            uri,
            serverSelectionTimeoutMS=3000,  # 3s timeout — don't block startup
            connectTimeoutMS=3000,
        )

        # Verify connection before storing
        client.admin.command("ping")

        db = client[db_name]
        _MODULE._mongo_client = client
        _MODULE._mongo_db = db

        _ensure_indexes(db)

        log.info(f"[memory] MongoDB connected — database: '{db_name}'")
        print(f"[memory] MongoDB connected — database: '{db_name}'")
        return client

    except ImportError:
        log.warning(
            "[memory] pymongo not installed. Run: pip install pymongo\n"
            "Memory layer disabled — workflow continues normally."
        )
        _MODULE._mongo_client = None
        _MODULE._mongo_db = None
        return None

    except Exception as e:
        log.warning(
            f"[memory] MongoDB connection failed: {e}\n"
            "Memory layer disabled — workflow continues normally."
        )
        _MODULE._mongo_client = None
        _MODULE._mongo_db = None
        return None


def get_mongo_db():
    """
    Return the MongoDB database object directly.
    Returns None if MongoDB is not configured or connection failed.
    """
    if not hasattr(_MODULE, "_mongo_db"):
        get_mongo_client()  # initializes _mongo_db as side effect
    return getattr(_MODULE, "_mongo_db", None)


def _ensure_indexes(db) -> None:
    """
    Create indexes on first connection.
    All indexes are created with background=True so startup isn't blocked.
    """
    try:
        # creator_memory: one document per user, indexed by user_id
        db.creator_memory.create_index("user_id", unique=True, background=True)
        db.creator_memory.create_index("channel_id", background=True)

        # research_sessions: many per user, ordered by created_at
        db.research_sessions.create_index(
            [("user_id", 1), ("created_at", -1)], background=True
        )
        db.research_sessions.create_index("topic", background=True)
        db.research_sessions.create_index("generation_id", background=True)

        # content_pieces: one per generation_id
        db.content_pieces.create_index("generation_id", unique=True, background=True)
        db.content_pieces.create_index(
            [("user_id", 1), ("created_at", -1)], background=True
        )

        log.info("[memory] MongoDB indexes created/verified")

    except Exception as e:
        log.warning(f"[memory] Index creation warning (non-fatal): {e}")
