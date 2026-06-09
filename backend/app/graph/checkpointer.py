"""
checkpointer.py — PostgreSQL-backed LangGraph checkpointer

Root cause of the previous bug:
    PostgresSaver.from_conn_string() returns a context manager.
    When used WITHOUT a `with` block the connection is opened but
    immediately eligible for cleanup — psycopg closes it as soon as
    the internal connection object goes out of scope.
    Subsequent calls to checkpointer.get_tuple() / put_writes() then
    crash with: psycopg.OperationalError: the connection is closed

Fix:
    Open a dedicated psycopg connection that we own and keep alive for
    the entire application lifetime.  Pass that connection directly to
    PostgresSaver().  Register a FastAPI lifespan shutdown hook that
    closes it cleanly when the server stops.

Two connection modes depending on what's installed:
    1. psycopg (v3, preferred) — PostgresSaver(conn)
    2. psycopg2 (v2, fallback) — ShallowConnection shim

If neither is available, falls back to MemorySaver with a clear warning.
"""
import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

_MODULE = sys.modules[__name__]

# ── Build the connection string ───────────────────────────────────

_raw_url: str = (
    os.getenv("DATABASE_URl", "") or os.getenv("DATABASE_URL", "")
).strip().strip('"')

# Strip SQLAlchemy driver prefixes — psycopg(3) uses plain postgresql://
_pg_url: str = (
    _raw_url
    .replace("postgresql+psycopg2://", "postgresql://")
    .replace("postgresql+psycopg://",  "postgresql://")
)

if not _pg_url:
    raise RuntimeError(
        "DATABASE_URl is not set in .env — "
        "cannot initialize PostgreSQL checkpointer."
    )


# ── Connection holder ────────────────────────────────────────────
# We own this connection for the app lifetime.
# It is closed by shutdown_checkpointer() in the FastAPI lifespan.

_raw_connection = None   # psycopg.Connection or psycopg2 connection


# ── Public API ───────────────────────────────────────────────────

def get_checkpointer():
    """
    Return the singleton PostgresSaver (or MemorySaver fallback).
    Safe to call multiple times — returns the same instance.
    Initializes on first call.
    """
    if hasattr(_MODULE, "_checkpointer") and _MODULE._checkpointer is not None:
        return _MODULE._checkpointer

    _MODULE._checkpointer = _initialize_checkpointer()
    return _MODULE._checkpointer


def setup_checkpointer() -> None:
    """
    Called once from FastAPI lifespan startup.
    Initializes the checkpointer and runs table setup.
    """
    checkpointer = get_checkpointer()

    # Run setup() to create langgraph_checkpoints / blobs / writes tables
    try:
        checkpointer.setup()
        log.info("[checkpointer] LangGraph checkpoint tables ready")
        print("[checkpointer] LangGraph checkpoint tables ready")
    except AttributeError:
        pass   # MemorySaver has no setup()
    except Exception as e:
        log.warning(f"[checkpointer] setup() warning (tables may already exist): {e}")


def shutdown_checkpointer() -> None:
    """
    Called once from FastAPI lifespan shutdown.
    Closes the persistent psycopg connection cleanly.
    """
    global _raw_connection
    if _raw_connection is not None:
        try:
            _raw_connection.close()
            log.info("[checkpointer] PostgreSQL connection closed")
        except Exception:
            pass
        _raw_connection = None


# ── Initialization ───────────────────────────────────────────────

def _initialize_checkpointer():
    """
    Try psycopg v3 first, then psycopg2, then MemorySaver.
    Returns the initialized checkpointer.
    """
    result = _try_psycopg3()
    if result is not None:
        return result

    result = _try_psycopg2()
    if result is not None:
        return result

    return _fallback_memory_saver()


def _try_psycopg3():
    """
    Initialize with psycopg (v3) — the preferred path.

    psycopg v3 requires autocommit=True for LangGraph's PostgresSaver.
    We open a persistent connection with autocommit enabled and pass it
    directly to PostgresSaver(conn). The connection stays open until
    shutdown_checkpointer() is called.
    """
    global _raw_connection
    try:
        import psycopg
        from langgraph.checkpoint.postgres import PostgresSaver

        conn = psycopg.connect(
            _pg_url,
            autocommit=True,        # Required by LangGraph PostgresSaver
            prepare_threshold=None, # Avoid prepared statement conflicts with pgbouncer
        )
        _raw_connection = conn

        checkpointer = PostgresSaver(conn)

        print("[checkpointer] PostgresSaver (psycopg v3) initialized")
        print(f"[checkpointer] Connection: {conn.info.host}:{conn.info.port}/{conn.info.dbname}")
        log.info("[checkpointer] PostgresSaver (psycopg v3) initialized — HITL state persists")
        return checkpointer

    except ImportError:
        log.debug("[checkpointer] psycopg (v3) not available, trying psycopg2")
        return None
    except Exception as e:
        log.warning(f"[checkpointer] psycopg v3 init failed: {e}")
        return None


def _try_psycopg2():
    """
    Fallback: initialize with psycopg2 (v2).

    langgraph-checkpoint-postgres >= 2.x dropped native psycopg2 support.
    If it's still available as PostgresSaver, use it. Otherwise skip.
    """
    global _raw_connection
    try:
        import psycopg2
        from langgraph.checkpoint.postgres import PostgresSaver

        # psycopg2 connection — autocommit required
        conn = psycopg2.connect(_pg_url)
        conn.autocommit = True
        _raw_connection = conn

        checkpointer = PostgresSaver(conn)

        print("[checkpointer] PostgresSaver (psycopg2) initialized")
        log.info("[checkpointer] PostgresSaver (psycopg2) initialized")
        return checkpointer

    except ImportError:
        log.debug("[checkpointer] psycopg2 not available")
        return None
    except Exception as e:
        log.warning(f"[checkpointer] psycopg2 init failed: {e}")
        return None


def _fallback_memory_saver():
    """
    Last resort: in-memory checkpointer.
    HITL state will be lost on server restart.
    Prints a loud warning so the developer notices.
    """
    from langgraph.checkpoint.memory import MemorySaver

    warning = (
        "\n" + "=" * 60 + "\n"
        "[checkpointer] WARNING: Using MemorySaver (in-memory only)\n"
        "  HITL workflow state WILL be lost on server restart.\n"
        "  To fix: pip install psycopg[binary] langgraph-checkpoint-postgres\n"
        "  and ensure DATABASE_URl is set in .env\n"
        + "=" * 60
    )
    print(warning)
    log.warning(warning)

    return MemorySaver()
