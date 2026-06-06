from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.openapi.utils import get_openapi
import os

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

from app.database import Base, engine

# Register all models with SQLAlchemy before create_all
from app.models import user, youtube_account, youtube_video, creator_profile  # noqa: F401

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Content Studio",
    description="Multi-agent content creation platform for YouTube",
    version="1.0.0",
    swagger_ui_parameters={"persistAuthorization": True},
)

# Pull session secret from env — never hardcode
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "fallback-dev-only"),
)

# CORS — allows the frontend (any localhost port) to call the API
# In production, replace "*" with your actual frontend domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",   # React / Next.js default
        "http://localhost:5173",   # Vite default
        "http://localhost:4200",   # Angular default
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def custom_openapi():
    """
    Replace the default OAuth2PasswordBearer scheme (which forces a broken
    username/password form popup) with a plain HTTPBearer scheme so the
    Swagger UI 'Authorize' button accepts a raw JWT access token directly.

    How to use in Swagger UI:
      1. POST /auth/login  →  copy the access_token from the response
      2. Click 'Authorize' (top right)  →  paste the token  →  Authorize
      3. All secured routes will now send  Authorization: Bearer <token>
    """
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # Define the Bearer scheme
    schema.setdefault("components", {})
    schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Paste the access_token from /auth/login or /auth/google/callback",
        }
    }

    # Apply BearerAuth to EVERY operation so the lock icon shows on all routes
    for path_data in schema["paths"].values():
        for operation in path_data.values():
            if isinstance(operation, dict):
                operation["security"] = [{"BearerAuth": []}]

    # Global default so new routes inherit it automatically
    schema["security"] = [{"BearerAuth": []}]

    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi  # type: ignore[method-assign]

# Individual agent routes
app.include_router(ideas_router)
app.include_router(script_router)
app.include_router(thumbnail_router)
app.include_router(seo_router)
app.include_router(upload_router)
app.include_router(auth_router)
app.include_router(thread_router)
app.include_router(youtube_router)
app.include_router(creator_profile_router)

# Main agentic workflow (LangGraph-powered, with HITL)
app.include_router(workflow_router)
