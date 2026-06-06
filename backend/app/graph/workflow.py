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
# Loads the creator profile once at the start of the workflow
# and stores it in state so every agent can use it.

def load_profile_node(state: AgentState) -> dict:
    """
    Load the creator profile from DB for this user.
    If no profile exists, workflow continues with empty profile
    (agents fall back to generic output).
    """
    user_id = state.get("user_id")
    if not user_id:
        print("[load_profile_node] no user_id in state — skipping profile load")
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
            print(f"[load_profile_node] no profile found for user {user_id}")
            return {"creator_profile": {}}

        # Flatten profile into a dict all agents understand
        profile_dict = {
            "creator_niche":            ", ".join(profile.topics or []),
            "main_topics":              profile.topics or [],
            "topics":                   profile.topics or [],
            "audience":                 profile.audience or {},
            "audience_type":            (profile.audience or {}).get("audience_type", ""),
            "audience_level":           (profile.audience or {}).get("audience_level", "beginner"),
            "title_style":              profile.title_style or {},
            "description_style":        profile.description_style or {},
            "content_strengths":        [],
            "viral_patterns":           [],
            "channel_name":             profile.channel_name,
        }
        print(f"[load_profile_node] loaded profile for '{profile.channel_name}'")
        return {"creator_profile": profile_dict}
    finally:
        db.close()


# ── Nodes ────────────────────────────────────────────────────────

def research_node(state: AgentState):
    print("[research_node] starting...")
    result = research_agent(
        state["topic"],
        state.get("plan", "normal"),
        state.get("creator_profile", {}),
    )
    print("[research_node] done.")
    return {"research": result}


def human_approval_node(state: AgentState):
    print("[human_approval_node] pausing — waiting for human review...")
    approved = interrupt("Research complete. Approve to continue.")
    print(f"[human_approval_node] resumed — approved={approved}")
    return {"human_approved": approved}


def idea_node(state: AgentState):
    print("[idea_node] starting...")
    result = video_idea_agent(
        state["topic"],
        state.get("research", ""),
        state.get("plan", "normal"),
        state.get("creator_profile", {}),
    )
    print("[idea_node] done.")
    return {"ideas": result}


def idea_selection_node(state: AgentState):
    selected = interrupt({
        "type": "idea_selection",
        "ideas": state["ideas"]
    })
    return {"selected_idea": selected}


def script_node(state: AgentState):
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


def thumbnail_node(state: AgentState):
    print("[thumbnail_node] starting...")
    result = thumbnail_agent(
        state["topic"],
        state.get("script", ""),
        state.get("plan", "normal"),
        state.get("creator_profile", {}),
    )
    print("[thumbnail_node] done.")
    return {"thumbnail": result}


def seo_node(state: AgentState):
    print("[seo_node] starting...")
    result = seo_agent(
        state["topic"],
        state.get("script", ""),
        state.get("plan", "normal"),
        state.get("creator_profile", {}),
    )
    print("[seo_node] done.")
    return {"seo": result}


# ── Conditional edge ─────────────────────────────────────────────

def check_approval(state: AgentState):
    if state.get("human_approved") is True:
        return "approved"
    return "rejected"


# ── Graph construction ───────────────────────────────────────────

def _build_graph(checkpointer: MemorySaver):
    builder = StateGraph(AgentState)

    builder.add_node("load_profile",   load_profile_node)
    builder.add_node("research",       research_node)
    builder.add_node("human_approval", human_approval_node)
    builder.add_node("ideas",          idea_node)
    builder.add_node("idea_selection", idea_selection_node)
    builder.add_node("script",         script_node)
    builder.add_node("thumbnail",      thumbnail_node)
    builder.add_node("seo",            seo_node)

    builder.set_entry_point("load_profile")
    builder.add_edge("load_profile",   "research")
    builder.add_edge("research",       "human_approval")

    builder.add_conditional_edges(
        "human_approval",
        check_approval,
        {"approved": "ideas", "rejected": END}
    )

    builder.add_edge("ideas",          "idea_selection")
    builder.add_edge("idea_selection", "script")
    builder.add_edge("script",         "thumbnail")
    builder.add_edge("thumbnail",      "seo")
    builder.add_edge("seo",            END)

    return builder.compile(checkpointer=checkpointer)


# ── Singleton guard — survives uvicorn --reload ──────────────────

import sys as _sys

_MODULE = _sys.modules[__name__]

if not hasattr(_MODULE, "_checkpointer"):
    _MODULE._checkpointer = MemorySaver()

if not hasattr(_MODULE, "_graph"):
    _MODULE._graph = _build_graph(_MODULE._checkpointer)

checkpointer: MemorySaver = _MODULE._checkpointer
graph = _MODULE._graph
