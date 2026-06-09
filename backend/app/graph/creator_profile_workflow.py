"""
creator_profile_workflow.py — Creator Profile Generation Pipeline

Graph: channel_fetch → video_fetch → creator_profile → save_profile → END

After save_profile, also syncs the full LLM output (including
content_strengths and viral_patterns) to MongoDB creator_memory
so agents can read real values instead of empty lists.
"""
from langgraph.graph import StateGraph, START, END
from sqlalchemy.orm import Session

from app.graph.state import CreatorProfileState
from app.services.youtube_service import get_channel_info, get_recent_videos
from app.agents.creator_profile_agent import creator_profile_agent, CreatorProfileAgent
from app.services.profile_service import save_creator_profile
from app.database import SessionLocal


def channel_fetch_node(state: CreatorProfileState) -> dict:
    db: Session = SessionLocal()
    try:
        channel_info = get_channel_info(user_id=state["user_id"], db=db)
    finally:
        db.close()
    return {"channel_info": channel_info}


def video_fetch_node(state: CreatorProfileState) -> dict:
    db: Session = SessionLocal()
    try:
        videos = get_recent_videos(
            user_id=state["user_id"],
            db=db,
            max_results=30,
        )
    finally:
        db.close()
    return {"videos": videos}


def creator_profile_node(state: CreatorProfileState) -> dict:
    """Run LLM analysis. Output validated by Pydantic."""
    profile_output = creator_profile_agent(
        channel_info=state["channel_info"],
        videos=state.get("videos", []),
    )
    return {"creator_profile": profile_output.model_dump()}


def save_profile_node(state: CreatorProfileState) -> dict:
    """
    1. Save to PostgreSQL (authoritative)
    2. Sync to MongoDB creator_memory (learning store — fixes viral_patterns bug)
    """
    db: Session = SessionLocal()
    try:
        profile = save_creator_profile(
            channel_info=state["channel_info"],
            creator_profile=state["creator_profile"],
            user_id=state["user_id"],
            db=db,
        )
    finally:
        db.close()

    # Sync full LLM output to MongoDB so viral_patterns is populated
    user_id      = state["user_id"]
    channel_info = state["channel_info"]
    profile_data = state["creator_profile"]

    try:
        from app.memory import get_creator_memory_service
        svc = get_creator_memory_service()
        svc.sync_from_profile(
            user_id=user_id,
            profile_data={
                **profile_data,
                # Ensure top-level keys match what sync_from_profile expects
                "creator_niche": profile_data.get("creator_niche", ""),
                "main_topics":   profile_data.get("main_topics", []),
                "topics":        profile_data.get("main_topics", []),
            },
            channel_id=channel_info.get("channel_id", ""),
            channel_name=channel_info.get("channel_name", ""),
        )
        print(
            f"[creator_profile_workflow] MongoDB sync complete — "
            f"viral_patterns={len(profile_data.get('viral_patterns', []))}"
        )
    except Exception as e:
        print(f"[creator_profile_workflow] MongoDB sync warning (non-fatal): {e}")

    return {"profile_id": profile.id}


# ── Graph ─────────────────────────────────────────────────────────────────────

builder = StateGraph(CreatorProfileState)

builder.add_node("channel_fetch",   channel_fetch_node)
builder.add_node("video_fetch",     video_fetch_node)
builder.add_node("creator_profile", creator_profile_node)
builder.add_node("save_profile",    save_profile_node)

builder.add_edge(START,             "channel_fetch")
builder.add_edge("channel_fetch",   "video_fetch")
builder.add_edge("video_fetch",     "creator_profile")
builder.add_edge("creator_profile", "save_profile")
builder.add_edge("save_profile",    END)

graph = builder.compile()
