"""
workflow.py — Content Generation Pipeline

Graph:
  load_memory → research → human_approval → ideas →
  idea_selection → script → thumbnail → save_generation → END

Key changes from previous version:
  - load_profile_node replaced by load_memory_node
    → reads PostgreSQL creator_profiles (authoritative)
    → syncs to MongoDB creator_memory (learning store)
    → merges memory context (viral_patterns, hooks, topic_history)
    → fixes the silent bug: content_strengths and viral_patterns are now
      populated from real LLM output, not hardcoded to []

  - research_node now saves to MongoDB research_sessions

  - save_generation_node now saves to MongoDB content_pieces and
    updates creator_memory counters
"""
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt

from app.graph.state import AgentState
from app.graph.checkpointer import get_checkpointer

from app.agents.research_agent import research_agent
from app.agents.video_idea_agent import video_idea_agent
from app.agents.script_agent import script_agent
from app.agents.thumbnail_agent import thumbnail_agent


# ── Memory node — replaces load_profile_node ─────────────────────

def load_memory_node(state: AgentState) -> dict:
    """
    1. Load creator profile from PostgreSQL (authoritative source)
    2. Sync it into MongoDB creator_memory (learning store)
    3. Read accumulated memory context (viral_patterns, hooks, topic_history)
    4. Merge everything into creator_profile in state

    This fixes the silent bug where content_strengths and viral_patterns
    were always [] because load_profile_node hardcoded them.
    """
    user_id = state.get("user_id")
    if not user_id:
        return {"creator_profile": {}}

    from app.database import SessionLocal
    from app.models.creator_profile import CreatorProfile
    from app.memory import get_creator_memory_service

    db = SessionLocal()
    try:
        # Step 1: PostgreSQL — authoritative profile data
        pg_profile = (
            db.query(CreatorProfile)
            .filter(CreatorProfile.user_id == user_id)
            .first()
        )

        if not pg_profile:
            print(f"[load_memory_node] no profile for user {user_id} — run /creator-profile/generate first")
            return {"creator_profile": {}}

        # Build the base profile dict from PostgreSQL
        base_profile = {
            "creator_niche":     ", ".join(pg_profile.topics or []),
            "main_topics":       pg_profile.topics or [],
            "topics":            pg_profile.topics or [],
            "audience":          pg_profile.audience or {},
            "audience_type":     (pg_profile.audience or {}).get("audience_type", ""),
            "audience_level":    (pg_profile.audience or {}).get("audience_level", "beginner"),
            "title_style":       pg_profile.title_style or {},
            "description_style": pg_profile.description_style or {},
            "channel_name":      pg_profile.channel_name,
            # Bug fix: content_strengths and viral_patterns are NOT set here.
            # They come from MongoDB memory below, where real LLM output is stored.
        }

        # Step 2: MongoDB sync — keep memory in sync with PostgreSQL
        memory_svc = get_creator_memory_service()
        memory_svc.sync_from_profile(
            user_id=user_id,
            profile_data=base_profile,
            channel_id=pg_profile.channel_id,
            channel_name=pg_profile.channel_name,
        )

        # Step 3: Read accumulated memory context
        # This is where content_strengths and viral_patterns actually come from
        memory_ctx = memory_svc.get_context_for_agents(user_id)

        # Step 4: Merge — PostgreSQL base + MongoDB accumulated learning
        merged_profile = {**base_profile, **memory_ctx}

        print(
            f"[load_memory_node] loaded profile for '{pg_profile.channel_name}' | "
            f"viral_patterns={len(memory_ctx.get('viral_patterns', []))} | "
            f"content_strengths={len(memory_ctx.get('content_strengths', []))} | "
            f"topic_history={len(memory_ctx.get('topic_history', []))} | "
            f"successful_hooks={len(memory_ctx.get('successful_hooks', []))}"
        )

        return {
            "creator_profile":          merged_profile,
            # Also surface key memory fields as top-level state for agents
            "viral_patterns":           memory_ctx.get("viral_patterns", []),
            "content_strengths":        memory_ctx.get("content_strengths", []),
            "successful_hooks":         memory_ctx.get("successful_hooks", []),
            "successful_title_patterns":memory_ctx.get("successful_title_patterns", []),
            "topic_history":            memory_ctx.get("topic_history", []),
            "audience_intelligence":    memory_ctx.get("audience_intelligence", {}),
        }

    finally:
        db.close()


# ── Research ─────────────────────────────────────────────────────

def research_node(state: AgentState) -> dict:
    print("[research_node] starting...")

    result = research_agent(
        topic=state["topic"],
        plan=state.get("plan", "normal"),
        creator_profile=state.get("creator_profile", {}),
        topic_history=state.get("topic_history", []),
    )
    print("[research_node] done.")

    generation_id = state.get("generation_id")
    user_id = state.get("user_id")

    # Persist research to PostgreSQL immediately
    if generation_id:
        from app.database import SessionLocal
        from app.services.generation_service import save_research
        db = SessionLocal()
        try:
            save_research(generation_id, result, db)
        finally:
            db.close()

    # Save research session to MongoDB memory
    if user_id and generation_id:
        try:
            from app.memory import get_research_memory_service
            get_research_memory_service().save_session(
                user_id=user_id,
                generation_id=generation_id,
                topic=state["topic"],
                research_output=result,
            )
            # Update topic history in creator_memory
            from app.memory import get_creator_memory_service
            get_creator_memory_service().add_topic(user_id, state["topic"])
        except Exception as e:
            print(f"[research_node] memory save warning (non-fatal): {e}")

    return {"research": result}


# ── HITL #1 ───────────────────────────────────────────────────────

def human_approval_node(state: AgentState) -> dict:
    print("[human_approval_node] pausing...")
    approved = interrupt("Research complete. Approve to continue.")
    print(f"[human_approval_node] resumed — approved={approved}")
    return {"human_approved": approved}


# ── Ideas ────────────────────────────────────────────────────────

def idea_node(state: AgentState) -> dict:
    print("[idea_node] starting...")
    result = video_idea_agent(
        topic=state["topic"],
        research=state.get("research", ""),
        plan=state.get("plan", "normal"),
        creator_profile=state.get("creator_profile", {}),
        past_topics=state.get("topic_history", []),
        successful_title_patterns=state.get("successful_title_patterns", []),
    )
    print("[idea_node] done.")
    return {"ideas": result}


# ── HITL #2 ───────────────────────────────────────────────────────

def idea_selection_node(state: AgentState) -> dict:
    selected = interrupt({"type": "idea_selection", "ideas": state["ideas"]})
    return {"selected_idea": selected}


# ── Script ───────────────────────────────────────────────────────

def script_node(state: AgentState) -> dict:
    print("[script_node] starting...")
    result = script_agent(
        topic=state["topic"],
        research=state.get("research", ""),
        selected_idea=state["selected_idea"],
        plan=state.get("plan", "normal"),
        creator_profile=state.get("creator_profile", {}),
        successful_hooks=state.get("successful_hooks", []),
    )
    print("[script_node] done.")
    return {"script": result}


# ── Thumbnail ────────────────────────────────────────────────────

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


# ── Save generation ───────────────────────────────────────────────

def save_generation_node(state: AgentState) -> dict:
    generation_id = state.get("generation_id")
    user_id = state.get("user_id")

    if not generation_id:
        print("[save_generation_node] no generation_id — skipping")
        return {}

    # Save to PostgreSQL
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

    # Save to MongoDB memory (non-fatal if fails)
    if user_id:
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

    return {}


# ── Conditional edges ─────────────────────────────────────────────

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


# ── Graph construction ────────────────────────────────────────────

def _build_graph(checkpointer):
    builder = StateGraph(AgentState)

    builder.add_node("load_memory",     load_memory_node)      # was load_profile
    builder.add_node("research",        research_node)
    builder.add_node("human_approval",  human_approval_node)
    builder.add_node("ideas",           idea_node)
    builder.add_node("idea_selection",  idea_selection_node)
    builder.add_node("script",          script_node)
    builder.add_node("thumbnail",       thumbnail_node)
    builder.add_node("save_generation", save_generation_node)
    builder.add_node("handle_rejection",handle_rejection_node)

    builder.set_entry_point("load_memory")
    builder.add_edge("load_memory",     "research")
    builder.add_edge("research",        "human_approval")

    builder.add_conditional_edges(
        "human_approval",
        check_approval,
        {"approved": "ideas", "rejected": "handle_rejection"},
    )

    builder.add_edge("handle_rejection","END" if False else END)
    builder.add_edge("ideas",           "idea_selection")
    builder.add_edge("idea_selection",  "script")
    builder.add_edge("script",          "thumbnail")
    builder.add_edge("thumbnail",       "save_generation")
    builder.add_edge("save_generation", END)

    return builder.compile(checkpointer=checkpointer)


# ── Singleton — built once after FastAPI lifespan startup ─────────

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
