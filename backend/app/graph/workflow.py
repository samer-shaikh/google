from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt

from app.graph.state import AgentState

from app.agents.research_agent import research_agent
from app.agents.video_idea_agent import video_idea_agent
from app.agents.script_agent import script_agent
from app.agents.thumbnail_agent import thumbnail_agent
from app.agents.seo_agent import seo_agent


# ── Profile loader ───────────────────────────────────────────────

def load_profile_node(state: AgentState) -> dict:
    user_id = state.get("user_id")
    if not user_id:
        return {"creator_profile": {}}

    from app.database import SessionLocal
    from app.models.creator_profile import CreatorProfile

    db = SessionLocal()
    try:
        profile = (
            db.query(CreatorProfile)
            .filter(CreatorProfile.user_id == user_id)
            .first()
        )
        if not profile:
            print(f"[load_profile_node] no profile for user {user_id}")
            return {"creator_profile": {}}

        profile_dict = {
            "creator_niche":    ", ".join(profile.topics or []),
            "main_topics":      profile.topics or [],
            "topics":           profile.topics or [],
            "audience":         profile.audience or {},
            "audience_type":    (profile.audience or {}).get("audience_type", ""),
            "audience_level":   (profile.audience or {}).get("audience_level", "beginner"),
            "title_style":      profile.title_style or {},
            "description_style":profile.description_style or {},
            "content_strengths":[],
            "viral_patterns":   [],
            "channel_name":     profile.channel_name,
        }
        print(f"[load_profile_node] loaded profile for '{profile.channel_name}'")
        return {"creator_profile": profile_dict}
    finally:
        db.close()


# ── Research ─────────────────────────────────────────────────────

def research_node(state: AgentState) -> dict:
    print("[research_node] starting...")
    result = research_agent(
        state["topic"],
        state.get("plan", "normal"),
        state.get("creator_profile", {}),
    )
    print("[research_node] done.")

    # Save research to DB immediately — if the user rejects later,
    # we still have a record of the research that was done
    generation_id = state.get("generation_id")
    if generation_id:
        from app.database import SessionLocal
        from app.services.generation_service import save_research
        db = SessionLocal()
        try:
            save_research(generation_id, result, db)
        finally:
            db.close()

    return {"research": result}


# ── HITL #1 — Research approval ──────────────────────────────────

def human_approval_node(state: AgentState) -> dict:
    print("[human_approval_node] pausing...")
    approved = interrupt("Research complete. Approve to continue.")
    print(f"[human_approval_node] resumed — approved={approved}")
    return {"human_approved": approved}


# ── Ideas ────────────────────────────────────────────────────────

def idea_node(state: AgentState) -> dict:
    print("[idea_node] starting...")
    result = video_idea_agent(
        state["topic"],
        state.get("research", ""),
        state.get("plan", "normal"),
        state.get("creator_profile", {}),
    )
    print("[idea_node] done.")
    return {"ideas": result}


# ── HITL #2 — Idea selection ─────────────────────────────────────

def idea_selection_node(state: AgentState) -> dict:
    selected = interrupt({
        "type":  "idea_selection",
        "ideas": state["ideas"],
    })
    return {"selected_idea": selected}


# ── Script ───────────────────────────────────────────────────────

def script_node(state: AgentState) -> dict:
    print("[script_node] starting...")
    result = script_agent(
        state["topic"],
        state.get("research", ""),
        state["selected_idea"],
        state.get("plan", "normal"),
        state.get("creator_profile", {}),
    )
    print("[script_node] done.")
    return {"script": result}


# ── Thumbnail ────────────────────────────────────────────────────

def thumbnail_node(state: AgentState) -> dict:
    print("[thumbnail_node] starting...")
    result = thumbnail_agent(
        state["topic"],
        state.get("script", ""),
        state.get("plan", "normal"),
        state.get("creator_profile", {}),
    )
    print("[thumbnail_node] done.")
    return {"thumbnail": result}


# ── SEO ──────────────────────────────────────────────────────────

def seo_node(state: AgentState) -> dict:
    print("[seo_node] starting...")
    result = seo_agent(
        state["topic"],
        state.get("script", ""),
        state.get("plan", "normal"),
        state.get("creator_profile", {}),
    )
    print("[seo_node] done.")
    return {"seo": result}


# ── Save generation ───────────────────────────────────────────────

def save_generation_node(state: AgentState) -> dict:
    """
    Final node — saves the complete workflow output to the
    generations table. Runs after SEO, before END.
    """
    generation_id = state.get("generation_id")
    if not generation_id:
        print("[save_generation_node] no generation_id in state — skipping save")
        return {}

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
            seo=state.get("seo", ""),
            creator_profile_snapshot=state.get("creator_profile", {}),
            db=db,
        )
        print(f"[save_generation_node] generation {generation_id} saved as completed")
    except Exception as e:
        print(f"[save_generation_node] error saving generation: {e}")
        try:
            fail_generation(generation_id, str(e), db)
        except Exception:
            pass
    finally:
        db.close()

    return {}


# ── Conditional edge ─────────────────────────────────────────────

def check_approval(state: AgentState) -> str:
    if state.get("human_approved") is True:
        return "approved"
    return "rejected"


def handle_rejection_node(state: AgentState) -> dict:
    """Mark generation as failed when user rejects research."""
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


# ── Graph construction ───────────────────────────────────────────

def _build_graph(checkpointer: MemorySaver):
    builder = StateGraph(AgentState)

    builder.add_node("load_profile",    load_profile_node)
    builder.add_node("research",        research_node)
    builder.add_node("human_approval",  human_approval_node)
    builder.add_node("ideas",           idea_node)
    builder.add_node("idea_selection",  idea_selection_node)
    builder.add_node("script",          script_node)
    builder.add_node("thumbnail",       thumbnail_node)
    builder.add_node("seo",             seo_node)
    builder.add_node("save_generation", save_generation_node)
    builder.add_node("handle_rejection",handle_rejection_node)

    builder.set_entry_point("load_profile")
    builder.add_edge("load_profile",   "research")
    builder.add_edge("research",       "human_approval")

    builder.add_conditional_edges(
        "human_approval",
        check_approval,
        {"approved": "ideas", "rejected": "handle_rejection"}
    )

    builder.add_edge("handle_rejection", END)
    builder.add_edge("ideas",            "idea_selection")
    builder.add_edge("idea_selection",   "script")
    builder.add_edge("script",           "thumbnail")
    builder.add_edge("thumbnail",        "seo")
    builder.add_edge("seo",              "save_generation")
    builder.add_edge("save_generation",  END)

    return builder.compile(checkpointer=checkpointer)


# ── Singleton — survives uvicorn --reload ────────────────────────

import sys as _sys
_MODULE = _sys.modules[__name__]

if not hasattr(_MODULE, "_checkpointer"):
    _MODULE._checkpointer = MemorySaver()

if not hasattr(_MODULE, "_graph"):
    _MODULE._graph = _build_graph(_MODULE._checkpointer)

checkpointer: MemorySaver = _MODULE._checkpointer
graph = _MODULE._graph
