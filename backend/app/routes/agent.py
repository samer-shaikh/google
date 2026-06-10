"""
app/routes/agent.py

API routes for intelligence agents — content gaps, trends, competitor ingestion.

All routes are async — FastAPI runs them on the event loop, so blocking
MongoDB/Elastic/LLM calls are offloaded via asyncio.to_thread() so the
server stays responsive during slow operations.

Endpoints:
  POST /agent/content-gap          — analyse content gaps for current user
  POST /agent/trends/refresh       — re-fetch trending topics for user's niche
  POST /agent/competitors/refresh  — re-ingest competitor videos for user's niche
  POST /agent/seed                 — seed Elastic with demo data (dev/hackathon use)
  GET  /agent/memory               — read user's full creator_memory document
  GET  /agent/memory/gaps          — read saved content gaps from MongoDB
  GET  /agent/memory/research      — read recent research sessions
  POST /agent/memory/hook          — manually add a successful hook
  POST /agent/memory/pattern       — manually add a successful title pattern
  GET  /agent/status               — health check for MongoDB + Elastic MCP layers
"""
import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.dependencies.auth import get_current_user
from app.models.user import User

log = logging.getLogger(__name__)
router = APIRouter(prefix="/agent", tags=["agent-intelligence"])


# ── Request models ────────────────────────────────────────────────────────────

class ContentGapRequest(BaseModel):
    niche: Optional[str] = None
    plan: str = "normal"

class AddHookRequest(BaseModel):
    hook: str

class AddPatternRequest(BaseModel):
    pattern: str

class SeedRequest(BaseModel):
    niche: str


# ── Content gap analysis ──────────────────────────────────────────────────────

@router.post("/content-gap")
async def get_content_gaps(
    data: ContentGapRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Analyse content gaps for the current user.
    Async: MongoDB niche lookup + LLM call run via asyncio.to_thread
    so the event loop stays free during the ~5s LLM call.
    """
    user_id = current_user.id

    # Resolve niche — offload blocking PyMongo call to thread
    niche = data.niche
    if not niche:
        try:
            def _get_niche():
                from app.mcp.mongodb.tools import find_one
                doc = find_one("creator_memory", {"user_id": user_id})
                return (doc or {}).get("profile", {}).get("niche", "")
            niche = await asyncio.to_thread(_get_niche)
        except Exception:
            pass

    if not niche:
        raise HTTPException(
            status_code=400,
            detail="Niche not found. Pass 'niche' in the request body "
                   "or complete the creator profile setup first.",
        )

    # Run content_gap_agent in thread — it does blocking LLM + DB calls
    from app.agents.content_gap_agent import content_gap_agent
    gaps = await asyncio.to_thread(
        content_gap_agent,
        user_id=user_id,
        niche=niche,
        plan=data.plan,
    )

    return {"user_id": user_id, "niche": niche, "count": len(gaps), "gaps": gaps}


# ── Trend refresh ─────────────────────────────────────────────────────────────

@router.post("/trends/refresh")
async def refresh_trends(current_user: User = Depends(get_current_user)):
    """
    Re-fetch and index trending topics for the current user's niche.
    Async: Elastic indexing + optional YouTube API call run in thread.
    """
    from app.agents.trend_agent import run_trend_agent_for_user
    result = await asyncio.to_thread(run_trend_agent_for_user, current_user.id)
    return {"user_id": current_user.id, **result}


# ── Competitor refresh ────────────────────────────────────────────────────────

@router.post("/competitors/refresh")
async def refresh_competitors(current_user: User = Depends(get_current_user)):
    """
    Re-ingest competitor content for the current user's niche.
    Async: YouTube API + Elastic indexing run in thread.
    """
    from app.jobs.competitor_ingestion import run_competitor_ingestion_for_user
    result = await asyncio.to_thread(run_competitor_ingestion_for_user, current_user.id)
    return {"user_id": current_user.id, **result}


# ── Seed demo data ────────────────────────────────────────────────────────────

@router.post("/seed")
async def seed_demo_data(
    data: SeedRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Seed Elasticsearch with demo competitor + audience question data.
    Async: all Elastic bulk-index calls run in thread pool.
    """
    from app.mcp.elastic.client import is_elastic_enabled
    if not is_elastic_enabled():
        return {
            "seeded": False,
            "reason": "Elasticsearch not configured. Add ELASTICSEARCH_URL to .env to enable.",
        }

    niche = data.niche

    def _seed():
        from app.jobs.trend_ingestion import seed_competitor_data, seed_audience_questions
        from app.agents.trend_agent import run_trend_agent
        competitors   = seed_competitor_data(niche)
        questions     = seed_audience_questions(niche)
        trends_result = run_trend_agent(niche, force_seeds=True)
        return competitors, questions, trends_result

    competitors, questions, trends_result = await asyncio.to_thread(_seed)

    return {
        "seeded": True,
        "niche":  niche,
        "competitor_docs_indexed":    competitors,
        "audience_questions_indexed": questions,
        "trending_topics_indexed":    trends_result.get("indexed", 0),
    }


# ── Memory reads ──────────────────────────────────────────────────────────────

@router.get("/memory")
async def get_creator_memory(current_user: User = Depends(get_current_user)):
    """
    Return the full creator_memory document.
    Async: PyMongo network I/O offloaded to thread.
    """
    def _fetch():
        from app.mcp.mongodb.tools import find_one
        return find_one("creator_memory", {"user_id": current_user.id})

    try:
        doc = await asyncio.to_thread(_fetch)
        if not doc:
            return {
                "user_id": current_user.id,
                "message": "No memory document yet. Run the workflow first.",
            }
        doc.pop("_id", None)
        return doc
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MongoDB error: {e}")


@router.get("/memory/gaps")
async def get_content_gaps_from_memory(current_user: User = Depends(get_current_user)):
    """Return saved content gaps from MongoDB creator_memory."""
    def _fetch():
        from app.mcp.mongodb.tools import find_one
        return find_one("creator_memory", {"user_id": current_user.id})

    try:
        doc  = await asyncio.to_thread(_fetch)
        gaps = (doc or {}).get("content_gaps", [])
        return {"user_id": current_user.id, "gaps": gaps, "count": len(gaps)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MongoDB error: {e}")


@router.get("/memory/research")
async def get_research_history(
    limit: int = 10,
    current_user: User = Depends(get_current_user),
):
    """Return the most recent research sessions from MongoDB."""
    def _fetch():
        from app.memory import get_research_memory_service
        sessions = get_research_memory_service().get_recent_sessions(
            user_id=current_user.id, limit=limit
        )
        for s in sessions:
            s.pop("_id", None)
        return sessions

    try:
        sessions = await asyncio.to_thread(_fetch)
        return {"user_id": current_user.id, "count": len(sessions), "sessions": sessions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MongoDB error: {e}")


# ── Memory writes ─────────────────────────────────────────────────────────────

@router.post("/memory/hook")
async def add_hook(
    data: AddHookRequest,
    current_user: User = Depends(get_current_user),
):
    """Manually add a successful hook to creator memory."""
    if not data.hook.strip():
        raise HTTPException(status_code=400, detail="Hook cannot be empty.")

    def _write():
        from app.memory import get_creator_memory_service
        get_creator_memory_service().add_hook(current_user.id, data.hook.strip())

    await asyncio.to_thread(_write)
    return {"added": True, "hook": data.hook.strip()}


@router.post("/memory/pattern")
async def add_title_pattern(
    data: AddPatternRequest,
    current_user: User = Depends(get_current_user),
):
    """Manually add a successful title pattern to creator memory."""
    if not data.pattern.strip():
        raise HTTPException(status_code=400, detail="Pattern cannot be empty.")

    def _write():
        from app.memory import get_creator_memory_service
        get_creator_memory_service().add_title_pattern(current_user.id, data.pattern.strip())

    await asyncio.to_thread(_write)
    return {"added": True, "pattern": data.pattern.strip()}


# ── Status / health ───────────────────────────────────────────────────────────

@router.get("/status")
async def agent_intelligence_status():
    """
    Health check for the intelligence layer.
    Async: all 3 checks (MongoDB, Elastic, MCP) run concurrently via asyncio.gather
    so the total wait is max(slowest_check) instead of sum(all_checks).
    """
    from app.mcp.elastic.client import is_elastic_enabled

    # Run all 3 checks concurrently
    async def _check_mongodb() -> bool:
        def _ping():
            from app.mcp.mongodb.tools import find_one
            find_one("creator_memory", {})
            return True
        try:
            return await asyncio.to_thread(_ping)
        except Exception:
            return False

    async def _check_elastic() -> bool:
        def _ping():
            from app.mcp.elastic.client import get_elastic_client
            client = get_elastic_client()
            if client:
                return bool(client.ping())
            return False
        try:
            return await asyncio.to_thread(_ping)
        except Exception:
            return False

    async def _check_mcp() -> bool:
        try:
            from app.mcp.mongodb import mcp_runner
            return bool(mcp_runner._initialized)
        except Exception:
            return False

    # All 3 checks fire at the same time — total latency = slowest one
    mongodb_ok, elastic_ok, mongodb_mcp_ok = await asyncio.gather(
        _check_mongodb(),
        _check_elastic(),
        _check_mcp(),
    )

    return {
        "mongodb_direct":  mongodb_ok,
        "mongodb_mcp":     mongodb_mcp_ok,
        "elasticsearch":   elastic_ok,
        "elastic_enabled": is_elastic_enabled(),
        "summary": (
            "All systems operational"
            if (mongodb_ok and elastic_ok)
            else "MongoDB OK — Elastic not configured (Phase 2 feature)"
            if mongodb_ok
            else "Degraded — check .env configuration"
        ),
    }
