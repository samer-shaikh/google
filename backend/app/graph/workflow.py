"""
workflow.py — Content Generation Pipeline

Graph:
  load_memory → content_gap_check → research → human_approval → ideas →
  idea_selection → script → critic → thumbnail → save_generation → END

Key features:
  - load_memory_node      reads PostgreSQL + syncs/reads MongoDB creator_memory
  - content_gap_check     finds uncovered opportunities (MongoDB + Elastic)
  - research_node         enriched with trending topics (Elastic) + topic history
  - idea_node             enriched with competitor insights + title patterns
  - script_node           enriched with successful hooks from creator memory
  - critic_node           quality gate (score >= 7/10 to pass, max 2 retries)
  - thumbnail_node        uses real viral_patterns (no longer always [])
  - save_generation_node  writes to PostgreSQL + MongoDB + Elastic content_index
"""
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt

from app.graph.state import AgentState
from app.graph.checkpointer import get_checkpointer

from app.agents.research_agent import research_agent
from app.agents.video_idea_agent import video_idea_agent
from app.agents.script_agent import script_agent
from app.agents.thumbnail_agent import thumbnail_agent
from app.agents.critic_agent import critic_agent, MAX_RETRIES
from app.agents.content_gap_agent import content_gap_agent


# ── Memory node ───────────────────────────────────────────────────────────────

def load_memory_node(state: AgentState) -> dict:
    """
    1. Load creator profile from PostgreSQL (authoritative source)
    2. Sync to MongoDB creator_memory (learning store)
    3. Read accumulated memory context (viral_patterns, hooks, topic_history)
    4. Merge everything into creator_profile in state
    """
    user_id = state.get("user_id")
    if not user_id:
        return {"creator_profile": {}}

    from app.database import SessionLocal
    from app.models.creator_profile import CreatorProfile
    from app.memory import get_creator_memory_service

    db = SessionLocal()
    try:
        pg_profile = (
            db.query(CreatorProfile)
            .filter(CreatorProfile.user_id == user_id)
            .first()
        )

        if not pg_profile:
            print(f"[load_memory_node] no profile for user {user_id}")
            return {"creator_profile": {}}

        base_profile = {
            "user_id":           user_id,
            "creator_niche":     ", ".join(pg_profile.topics or []),
            "main_topics":       pg_profile.topics or [],
            "topics":            pg_profile.topics or [],
            "audience":          pg_profile.audience or {},
            "audience_type":     (pg_profile.audience or {}).get("audience_type", ""),
            "audience_level":    (pg_profile.audience or {}).get("audience_level", "beginner"),
            "title_style":       pg_profile.title_style or {},
            "description_style": pg_profile.description_style or {},
            "channel_name":      pg_profile.channel_name,
        }

        memory_svc = get_creator_memory_service()
        memory_svc.sync_from_profile(
            user_id=user_id,
            profile_data=base_profile,
            channel_id=pg_profile.channel_id,
            channel_name=pg_profile.channel_name,
        )

        memory_ctx = memory_svc.get_context_for_agents(user_id)
        merged_profile = {**base_profile, **memory_ctx}

        print(
            f"[load_memory_node] '{pg_profile.channel_name}' | "
            f"viral_patterns={len(memory_ctx.get('viral_patterns', []))} | "
            f"topic_history={len(memory_ctx.get('topic_history', []))} | "
            f"hooks={len(memory_ctx.get('successful_hooks', []))}"
        )

        return {
            "creator_profile":           merged_profile,
            "viral_patterns":            memory_ctx.get("viral_patterns", []),
            "content_strengths":         memory_ctx.get("content_strengths", []),
            "successful_hooks":          memory_ctx.get("successful_hooks", []),
            "successful_title_patterns": memory_ctx.get("successful_title_patterns", []),
            "topic_history":             memory_ctx.get("topic_history", []),
            "audience_intelligence":     memory_ctx.get("audience_intelligence", {}),
            "script_revision_count":     0,   # reset revision counter each run
        }

    finally:
        db.close()


# ── Content gap check ─────────────────────────────────────────────────────────

def content_gap_check_node(state: AgentState) -> dict:
    """
    Identify content opportunities this creator hasn't covered yet.
    Reads MongoDB topic_history + Elastic competitor/audience data.
    Results stored in state["content_gaps"] for use in research prompt.
    Non-blocking — if no data, returns empty list silently.
    """
    user_id = state.get("user_id")
    creator_profile = state.get("creator_profile", {})
    niche = creator_profile.get("creator_niche", "")

    if not user_id or not niche:
        return {"content_gaps": [], "trending_topics": [], "competitor_insights": []}

    try:
        gaps = content_gap_agent(
            user_id=user_id,
            niche=niche,
            plan=state.get("plan", "normal"),
            topic_history=state.get("topic_history", []),
        )
        gap_topics = [g.get("topic", "") for g in gaps if g.get("topic")]
        print(f"[content_gap_check_node] found {len(gaps)} content opportunities")
    except Exception as e:
        print(f"[content_gap_check_node] skipped (non-fatal): {e}")
        gap_topics = []

    # Fetch trending topics for research enrichment
    trending = []
    try:
        from app.mcp.elastic.tools import search_trending_topics
        raw = search_trending_topics(niche=niche, days=30, limit=8)
        trending = [t.get("topic", "") for t in raw if t.get("topic")]
    except Exception:
        pass

    # Fetch competitor insights for idea enrichment
    competitors = []
    try:
        from app.mcp.elastic.tools import search_competitor_content
        competitors = search_competitor_content(niche=niche, limit=8)
    except Exception:
        pass

    return {
        "content_gaps":       gap_topics,
        "trending_topics":    trending,
        "competitor_insights": competitors,
    }


# ── Research ──────────────────────────────────────────────────────────────────

def research_node(state: AgentState) -> dict:
    print("[research_node] starting...")

    topic_history = list(state.get("topic_history", []))
    trending      = state.get("trending_topics", [])
    content_gaps  = state.get("content_gaps", [])

    # Merge trending topics and content gaps into topic history context
    # so research_agent knows what's hot AND what gaps exist
    enriched_history = topic_history.copy()
    if trending:
        enriched_history = [f"[TRENDING] {t}" for t in trending[:5]] + enriched_history
    if content_gaps:
        enriched_history = [f"[GAP OPPORTUNITY] {g}" for g in content_gaps[:3]] + enriched_history

    result = research_agent(
        topic=state["topic"],
        plan=state.get("plan", "normal"),
        creator_profile=state.get("creator_profile", {}),
        topic_history=enriched_history,
    )
    print("[research_node] done.")

    generation_id = state.get("generation_id")
    user_id = state.get("user_id")

    if generation_id:
        from app.database import SessionLocal
        from app.services.generation_service import save_research
        db = SessionLocal()
        try:
            save_research(generation_id, result, db)
        finally:
            db.close()

    if user_id and generation_id:
        try:
            from app.memory import get_research_memory_service, get_creator_memory_service
            get_research_memory_service().save_session(
                user_id=user_id,
                generation_id=generation_id,
                topic=state["topic"],
                research_output=result,
            )
            get_creator_memory_service().add_topic(user_id, state["topic"])
        except Exception as e:
            print(f"[research_node] memory save warning (non-fatal): {e}")

    return {"research": result}


# ── HITL #1 ───────────────────────────────────────────────────────────────────

def human_approval_node(state: AgentState) -> dict:
    print("[human_approval_node] pausing...")
    approved = interrupt("Research complete. Approve to continue.")
    print(f"[human_approval_node] resumed — approved={approved}")
    return {"human_approved": approved}


# ── Ideas ─────────────────────────────────────────────────────────────────────

def idea_node(state: AgentState) -> dict:
    print("[idea_node] starting...")

    # Enrich successful_title_patterns with competitor insights
    title_patterns = list(state.get("successful_title_patterns", []))
    competitors = state.get("competitor_insights", [])
    if competitors:
        comp_titles = [c.get("title", "") for c in competitors[:5] if c.get("title")]
        print(f"[idea_node] injecting {len(comp_titles)} competitor titles as context")

    result = video_idea_agent(
        topic=state["topic"],
        research=state.get("research", ""),
        plan=state.get("plan", "normal"),
        creator_profile=state.get("creator_profile", {}),
        past_topics=state.get("topic_history", []),
        successful_title_patterns=title_patterns,
    )
    print("[idea_node] done.")
    return {"ideas": result}


# ── HITL #2 ───────────────────────────────────────────────────────────────────

def idea_selection_node(state: AgentState) -> dict:
    selected = interrupt({"type": "idea_selection", "ideas": state["ideas"]})
    return {"selected_idea": selected}


# ── Script ────────────────────────────────────────────────────────────────────

def script_node(state: AgentState) -> dict:
    print("[script_node] starting...")

    critique = state.get("script_critique", "")
    revision = state.get("script_revision_count", 0)

    # Inject critique into hooks context if this is a revision
    successful_hooks = list(state.get("successful_hooks", []))
    if critique and revision > 0:
        print(f"[script_node] revision #{revision} — injecting critique: {critique[:80]}...")

    result = script_agent(
        topic=state["topic"],
        research=state.get("research", ""),
        selected_idea=state["selected_idea"],
        plan=state.get("plan", "normal"),
        creator_profile=state.get("creator_profile", {}),
        successful_hooks=successful_hooks,
    )
    print("[script_node] done.")
    return {"script": result}


# ── Critic ────────────────────────────────────────────────────────────────────

def critic_node(state: AgentState) -> dict:
    """Quality gate — routes back to script_node if score < 7."""
    print("[critic_node] reviewing script...")

    revision_count = state.get("script_revision_count", 0)

    report = critic_agent(
        topic=state["topic"],
        selected_idea=state.get("selected_idea", ""),
        script=state.get("script", ""),
        plan=state.get("plan", "normal"),
        creator_profile=state.get("creator_profile", {}),
        revision_count=revision_count,
    )

    return {
        "script_quality_score":  report.get("total_score", 7),
        "script_critique":       report.get("critique", ""),
        "script_revision_count": revision_count + 1,
    }


def check_script_quality(state: AgentState) -> str:
    """Conditional edge: pass or revise."""
    score = state.get("script_quality_score", 7)
    revision = state.get("script_revision_count", 0)

    if score >= 7 or revision > MAX_RETRIES:
        print(f"[critic] PASSED — score={score} revision={revision}")
        return "pass"
    else:
        print(f"[critic] REVISE — score={score} revision={revision}")
        return "revise"


# ── Thumbnail ─────────────────────────────────────────────────────────────────

def thumbnail_node(state: AgentState) -> dict:
    print("[thumbnail_node] starting...")
    result = thumbnail_agent(
        topic=state["topic"],
        script=state.get("script", ""),
        plan=state.get("plan", "normal"),
        creator_profile=state.get("creator_profile", {}),
    )
    print("[thumbnail_node] done.")
    return {"thumbnail": result}


# ── Save generation ───────────────────────────────────────────────────────────

def save_generation_node(state: AgentState) -> dict:
    generation_id = state.get("generation_id")
    user_id = state.get("user_id")

    if not generation_id:
        print("[save_generation_node] no generation_id — skipping")
        return {}

    # ── Save to PostgreSQL (must succeed before MongoDB/Elastic) ──────────────
    from app.database import SessionLocal
    from app.services.generation_service import complete_generation, fail_generation

    db = SessionLocal()
    try:
        complete_generation(
            generation_id=generation_id,
            ideas=state.get("ideas", []),
            selected_idea=state.get("selected_idea", ""),
            script=state.get("script", ""),
            thumbnail=state.get("thumbnail", ""),
            seo="",
            creator_profile_snapshot=state.get("creator_profile", {}),
            db=db,
        )
        print(f"[save_generation_node] generation {generation_id} saved to PostgreSQL")
    except Exception as e:
        print(f"[save_generation_node] PostgreSQL save error: {e}")
        try:
            fail_generation(generation_id, str(e), db)
        except Exception:
            pass
        return {}
    finally:
        db.close()

    if not user_id:
        return {}

    # ── Save to MongoDB + Elastic concurrently using threads ──────────────────
    import concurrent.futures

    def _save_mongodb():
        try:
            from app.memory import get_content_memory_service, get_creator_memory_service
            get_content_memory_service().save_content_piece(
                user_id=user_id,
                generation_id=generation_id,
                topic=state.get("topic", ""),
                selected_idea=state.get("selected_idea", ""),
                script=state.get("script", ""),
                thumbnail=state.get("thumbnail", ""),
            )
            get_creator_memory_service().increment_generations(user_id)
            print(f"[save_generation_node] generation {generation_id} saved to MongoDB")
        except Exception as e:
            print(f"[save_generation_node] MongoDB save warning (non-fatal): {e}")

    def _save_elastic():
        try:
            from app.mcp.elastic.tools import index_content_piece
            import datetime
            index_content_piece({
                "user_id":       user_id,
                "generation_id": generation_id,
                "topic":         state.get("topic", ""),
                "selected_idea": state.get("selected_idea", ""),
                "script_hook":   state.get("script", "")[:200],
                "niche":         state.get("creator_profile", {}).get("creator_niche", ""),
                "created_at":    datetime.datetime.utcnow().isoformat(),
            })
            print(f"[save_generation_node] indexed generation {generation_id} to Elastic")
        except Exception as e:
            print(f"[save_generation_node] Elastic index warning (non-fatal): {e}")

    # Fire both saves in parallel — total time = max(mongo_time, elastic_time)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        mongo_f   = pool.submit(_save_mongodb)
        elastic_f = pool.submit(_save_elastic)
        # Wait for both — errors are caught inside each function
        concurrent.futures.wait([mongo_f, elastic_f], timeout=15.0)

    return {}


# ── Rejection handler ─────────────────────────────────────────────────────────

def check_approval(state: AgentState) -> str:
    return "approved" if state.get("human_approved") is True else "rejected"


def handle_rejection_node(state: AgentState) -> dict:
    generation_id = state.get("generation_id")
    if generation_id:
        from app.database import SessionLocal
        from app.services.generation_service import fail_generation
        db = SessionLocal()
        try:
            fail_generation(generation_id, "Rejected by user at research stage", db)
        finally:
            db.close()
    return {}


# ── Graph construction ────────────────────────────────────────────────────────

def _build_graph(checkpointer):
    builder = StateGraph(AgentState)

    builder.add_node("load_memory",       load_memory_node)
    builder.add_node("content_gap_check", content_gap_check_node)
    builder.add_node("research",          research_node)
    builder.add_node("human_approval",    human_approval_node)
    builder.add_node("ideas",             idea_node)
    builder.add_node("idea_selection",    idea_selection_node)
    builder.add_node("script",            script_node)
    builder.add_node("critic",            critic_node)
    builder.add_node("thumbnail",         thumbnail_node)
    builder.add_node("save_generation",   save_generation_node)
    builder.add_node("handle_rejection",  handle_rejection_node)

    builder.set_entry_point("load_memory")
    builder.add_edge("load_memory",       "content_gap_check")
    builder.add_edge("content_gap_check", "research")
    builder.add_edge("research",          "human_approval")

    builder.add_conditional_edges(
        "human_approval",
        check_approval,
        {"approved": "ideas", "rejected": "handle_rejection"},
    )

    builder.add_edge("handle_rejection", END)
    builder.add_edge("ideas",            "idea_selection")
    builder.add_edge("idea_selection",   "script")
    builder.add_edge("script",           "critic")

    # Critic conditional edge: pass → thumbnail, revise → script
    builder.add_conditional_edges(
        "critic",
        check_script_quality,
        {"pass": "thumbnail", "revise": "script"},
    )

    builder.add_edge("thumbnail",        "save_generation")
    builder.add_edge("save_generation",  END)

    return builder.compile(checkpointer=checkpointer)


# ── Singleton ─────────────────────────────────────────────────────────────────

import sys as _sys
_MODULE = _sys.modules[__name__]

graph = None


def init_content_graph():
    if not hasattr(_MODULE, "_graph") or _MODULE._graph is None:
        _MODULE._graph = _build_graph(get_checkpointer())
        print("[workflow] content generation graph compiled")
    import app.graph.workflow as _self
    _self.graph = _MODULE._graph
    return _MODULE._graph
