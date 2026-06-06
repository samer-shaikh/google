"""
checkpointer.py — PostgreSQL-backed LangGraph checkpointer

Replaces MemorySaver for all three graphs:
  - workflow.py          (content generation pipeline)
  - upload_workflow.py   (publishing pipeline)
  - creator_profile_workflow.py (no HITL, but benefits from persistence)

Why PostgreSQL instead of MemorySaver:
  - MemorySaver stores state in RAM — server restart = all paused workflows lost
  - PostgresSaver stores state in your existing PostgreSQL DB
  - Users can resume HITL workflows even after server restarts
  - Works correctly with multiple uvicorn workers

The checkpointer creates its own tables automatically on first use:
  - langgraph_checkpoints
  - langgraph_checkpoint_blobs
  - langgraph_checkpoint_writes

These are managed entirely by LangGraph — do NOT touch them manually.
"""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# ── Build the connection string ───────────────────────────────────
# LangGraph's PostgresSaver uses psycopg (v3), not psycopg2.
# The connection string format is the same as SQLAlchemy but
# we swap the scheme to "postgresql" (psycopg3 default).

_raw_url = os.getenv("DATABASE_URl") or os.getenv("DATABASE_URL", "")

# SQLAlchemy uses postgresql+psycopg2:// — strip the driver suffix
# so psycopg3 can use it directly
_pg_url = (
    _raw_url
    .replace("postgresql+psycopg2://", "postgresql://")
    .replace("postgresql+psycopg://",  "postgresql://")
    .strip('"')   # strip any accidental quotes from .env
)

if not _pg_url:
    raise RuntimeError(
        "DATABASE_URl is not set in .env — "
        "PostgreSQL checkpointer cannot be initialized"
    )


# ── Singleton factory ─────────────────────────────────────────────
# We use a module-level singleton so the connection pool is shared
# across all three graphs and survives uvicorn --reload.

_MODULE = sys.modules[__name__]


def get_checkpointer():
    """
    Return the singleton PostgresSaver instance.
    Creates and sets up the checkpointer tables on first call.
    Falls back to MemorySaver if the postgres package is not installed,
    printing a clear warning so the developer knows to install it.
    """
    if hasattr(_MODULE, "_checkpointer"):
        return _MODULE._checkpointer

    try:
        from langgraph.checkpoint.postgres import PostgresSaver

        checkpointer = PostgresSaver.from_conn_string(_pg_url)

        # Creates langgraph_checkpoints, langgraph_checkpoint_blobs,
        # langgraph_checkpoint_writes tables if they don't exist yet.
        checkpointer.setup()

        _MODULE._checkpointer = checkpointer
        print("[checkpointer] PostgresSaver initialized — HITL state persists across restarts")
        return checkpointer

    except ImportError:
        print(
            "[checkpointer] WARNING: langgraph-checkpoint-postgres not installed.\n"
            "  Run: pip install langgraph-checkpoint-postgres psycopg[binary]\n"
            "  Falling back to MemorySaver — HITL state will be lost on server restart."
        )
        from langgraph.checkpoint.memory import MemorySaver
        _MODULE._checkpointer = MemorySaver()
        return _MODULE._checkpointer

    except Exception as e:
        print(
            f"[checkpointer] WARNING: Could not connect to PostgreSQL: {e}\n"
            "  Falling back to MemorySaver."
        )
        from langgraph.checkpoint.memory import MemorySaver
        _MODULE._checkpointer = MemorySaver()
        return _MODULE._checkpointer
