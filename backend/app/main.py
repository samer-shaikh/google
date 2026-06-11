from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.openapi.utils import get_openapi
import os
from dotenv import load_dotenv

load_dotenv()


def _run_startup_trend_ingestion():
    """Background thread: seed trends for all creators on startup."""
    try:
        from app.jobs.trend_ingestion import run_trend_ingestion_for_all_users
        result = run_trend_ingestion_for_all_users()
        print(f"[trend_ingestion] startup complete: {result}")
    except Exception as e:
        print(f"[trend_ingestion] startup failed (non-fatal): {e}")

from app.routes.ideas import router as ideas_router
from app.routes.script import router as script_router
from app.routes.thumbnail import router as thumbnail_router
from app.routes.seo import router as seo_router
from app.routes.upload import router as upload_router
from app.routes.workflow import router as workflow_router
from app.routes.auth import router as auth_router
from app.routes.thread import router as thread_router
from app.routes.youtube import router as youtube_router
from app.routes.creator_profile import router as creator_profile_router
from app.routes.upload import router as upload_router
from app.routes.agent import router as agent_router

from app.database import Base, engine

# Register all models with SQLAlchemy before create_all
from app.models import user, youtube_account, youtube_video, creator_profile  # noqa: F401

Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan: runs startup code before the server accepts requests,
    and shutdown code after the last request is handled.

    Startup order matters:
      1. Initialize the PostgreSQL checkpointer (opens a persistent connection).
      2. Run checkpointer.setup() to create LangGraph tables if missing.
      3. Compile the LangGraph graphs (they need a live checkpointer).

    Shutdown order:
      1. Close the persistent checkpointer connection cleanly.

    Why lifespan instead of @app.on_event("startup"):
      - @app.on_event is deprecated in FastAPI >= 0.93.
      - lifespan guarantees the connection is open before ANY route handler runs.
      - lifespan guarantees clean shutdown even if a worker crashes.
    """
    # ── STARTUP ──────────────────────────────────────────────────
    print("[lifespan] starting up...")

    # Step 1: open the persistent PostgreSQL connection + create LG tables
    from app.graph.checkpointer import setup_checkpointer
    setup_checkpointer()

    # Step 2: initialize MongoDB memory layer (non-blocking — fails gracefully)
    from app.mcp.mongodb.client import get_mongodb_client
    get_mongodb_client()

    # Step 2b: pre-warm the MongoDB MCP server subprocess
    try:
        from app.mcp.mongodb.mcp_runner import call_mcp_tool
        result = await call_mcp_tool("find", {
            "collection": "creator_memory",
            "filter": {},
            "limit": 1,
        })
        if result is not None:
            print("[mcp_runner] ✅ MongoDB MCP server is ACTIVE and responding")
        else:
            print("[mcp_runner] ✅ MongoDB MCP server is ACTIVE (collection empty — normal on first run)")
    except Exception as e:
        print(f"[mcp_runner] ⚠️  MongoDB MCP server not available: {e} — falling back to PyMongo")

    # Step 2c: initialize Elasticsearch + create indexes if configured
    try:
        from app.mcp.elastic.client import get_elastic_client, is_elastic_enabled
        if is_elastic_enabled():
            client = get_elastic_client()
            if client:
                from app.mcp.elastic.indexes import setup_indexes
                setup_indexes()
                print("[elastic] ✅ Elasticsearch connected — indexes ready")

                # Pre-warm Elastic MCP subprocess if ELASTIC_MCP_URL is set
                import os
                if os.getenv("ELASTIC_MCP_URL", "").strip():
                    from app.mcp.elastic.mcp_runner import call_elastic_tool
                    await call_elastic_tool("search", {
                        "index": "trending_topics",
                        "query": {"match_all": {}},
                        "size": 1,
                    })
                    print("[elastic_mcp] ✅ Elasticsearch MCP server is ACTIVE")
        else:
            print("[elastic] ℹ️  ELASTICSEARCH_URL not set — trend intelligence disabled (add to .env to enable)")
    except Exception as e:
        print(f"[elastic] ⚠️  Elasticsearch startup warning: {e}")

    # Step 2d: run background trend ingestion if Elastic is ready
    try:
        from app.mcp.elastic.client import is_elastic_enabled
        if is_elastic_enabled():
            import asyncio
            loop = asyncio.get_event_loop()
            loop.run_in_executor(None, _run_startup_trend_ingestion)
    except Exception as e:
        print(f"[trend_ingestion] startup ingestion warning: {e}")

    # Step 3: compile graphs AFTER checkpointer connection is live
    from app.graph.workflow import init_content_graph
    from app.graph.upload_workflow import init_upload_graph
    init_content_graph()
    init_upload_graph()

    print("[lifespan] startup complete — server ready")
    yield
    # ── SHUTDOWN ─────────────────────────────────────────────────
    print("[lifespan] shutting down...")

    from app.graph.checkpointer import shutdown_checkpointer
    shutdown_checkpointer()

    # Gracefully stop MongoDB MCP subprocess if it was started
    try:
        from app.mcp.mongodb.mcp_runner import shutdown_mcp
        await shutdown_mcp()
        print("[mcp_runner] MongoDB MCP server stopped")
    except Exception:
        pass

    # Gracefully stop Elasticsearch MCP subprocess if it was started
    try:
        from app.mcp.elastic.mcp_runner import shutdown_elastic_mcp
        await shutdown_elastic_mcp()
        print("[elastic_mcp] Elasticsearch MCP server stopped")
    except Exception:
        pass

    print("[lifespan] shutdown complete")


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="AI Content Studio",
    description="Multi-agent content creation platform for YouTube",
    version="1.0.0",
    swagger_ui_parameters={"persistAuthorization": True},
    lifespan=lifespan,
)

# Pull session secret from env — never hardcode
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "fallback-dev-only"),
)

# CORS — allows the frontend (any localhost port) to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



def custom_openapi():
    """HTTPBearer scheme for Swagger UI — paste JWT access_token in Authorize."""
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    schema.setdefault("components", {})
    schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Paste the access_token from /auth/login",
        }
    }

    for path_data in schema["paths"].values():
        for operation in path_data.values():
            if isinstance(operation, dict):
                operation["security"] = [{"BearerAuth": []}]

    schema["security"] = [{"BearerAuth": []}]
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi  # type: ignore[method-assign]

@app.get("/ping")
def ping():
    return {"message": "Backend Connected"}

# Routers
app.include_router(ideas_router)
app.include_router(script_router)
app.include_router(thumbnail_router)
app.include_router(seo_router)
app.include_router(upload_router)
app.include_router(auth_router)
app.include_router(thread_router)
app.include_router(youtube_router)
app.include_router(creator_profile_router)
app.include_router(workflow_router)
app.include_router(upload_router)
app.include_router(agent_router)
