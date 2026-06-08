"""
app/memory/__init__.py

Memory layer for AI Content Studio.

Phase 1: MongoDB-backed creator memory.
  - CreatorMemoryService  — persistent creator profile + learning data
  - ResearchMemoryService — research session history per creator
  - ContentMemoryService  — generated content tracking per creator

All services are designed to degrade gracefully when MongoDB is not
configured. If MONGODB_URI is not set, every method is a no-op and
the workflow continues using PostgreSQL data only.

Usage:
    from app.memory import get_creator_memory_service
    svc = get_creator_memory_service()
    memory = svc.get_or_create(user_id=6, channel_name="Learn with Samer")
"""

from app.memory.creator_memory_service import CreatorMemoryService
from app.memory.research_memory_service import ResearchMemoryService
from app.memory.content_memory_service import ContentMemoryService
from app.memory.mongo_client import get_mongo_client, is_memory_enabled

_creator_svc: CreatorMemoryService | None = None
_research_svc: ResearchMemoryService | None = None
_content_svc: ContentMemoryService | None = None


def get_creator_memory_service() -> CreatorMemoryService:
    global _creator_svc
    if _creator_svc is None:
        _creator_svc = CreatorMemoryService(get_mongo_client())
    return _creator_svc


def get_research_memory_service() -> ResearchMemoryService:
    global _research_svc
    if _research_svc is None:
        _research_svc = ResearchMemoryService(get_mongo_client())
    return _research_svc


def get_content_memory_service() -> ContentMemoryService:
    global _content_svc
    if _content_svc is None:
        _content_svc = ContentMemoryService(get_mongo_client())
    return _content_svc
