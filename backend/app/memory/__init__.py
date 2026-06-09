"""
app/memory/__init__.py — Memory layer factory.

Usage anywhere in the codebase:
    from app.memory import get_creator_memory_service
    svc = get_creator_memory_service()
    ctx = svc.get_context_for_agents(user_id=6)
"""
import sys

_MODULE = sys.modules[__name__]


def get_creator_memory_service():
    if not hasattr(_MODULE, "_creator_svc"):
        from app.memory.creator_memory_service import CreatorMemoryService
        from app.mcp.mongodb.client import get_mongodb_client
        get_mongodb_client()  # ensure connection is initialized
        _MODULE._creator_svc = CreatorMemoryService()
    return _MODULE._creator_svc


def get_research_memory_service():
    if not hasattr(_MODULE, "_research_svc"):
        from app.memory.research_memory_service import ResearchMemoryService
        _MODULE._research_svc = ResearchMemoryService()
    return _MODULE._research_svc


def get_content_memory_service():
    if not hasattr(_MODULE, "_content_svc"):
        from app.memory.content_memory_service import ContentMemoryService
        _MODULE._content_svc = ContentMemoryService()
    return _MODULE._content_svc
