from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes.ideas import router as ideas_router
from app.routes.script import router as script_router
from app.routes.thumbnail import router as thumbnail_router
from app.routes.seo import router as seo_router
from app.routes.upload import router as upload_router
from app.routes.workflow import router as workflow_router

from app.database import Base, engine

from app.models.creator_profile import CreatorProfile

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Content Studio",
    description="Multi-agent content creation platform for YouTube",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Individual agent routes (kept for testing)
app.include_router(ideas_router)
app.include_router(script_router)
app.include_router(thumbnail_router)
app.include_router(seo_router)
app.include_router(upload_router)

# Main agentic workflow (LangGraph-powered, with HITL)
app.include_router(workflow_router)
