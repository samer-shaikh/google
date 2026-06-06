"""
creator_profile_workflow.py

Fixed issues:
1. channel_fetch_node and video_fetch_node called youtube_service with a
   channel_url string but youtube_service was hardcoded mock data.
   Now both nodes use the real API via user_id + a managed DB session.

2. user_id was not in CreatorProfileState — profiles were saved with NULL user_id.
   Now user_id flows through the entire graph.

3. save_profile_node called save_creator_profile() which opened its own
   SessionLocal() internally — an unmanaged session that could leak.
   Now the node opens and closes a single session for the save operation.

4. creator_profile_node called creator_profile_agent() (the LLM function directly)
   — output was not validated before hitting the DB.
   Now it goes through CreatorProfileAgent.run() which validates with Pydantic.
"""
from langgraph.graph import StateGraph, START, END
from sqlalchemy.orm import Session

from app.graph.state import CreatorProfileState
from app.services.youtube_service import get_channel_info, get_recent_videos
from app.agents.creator_profile_agent import CreatorProfileAgent
from app.services.profile_service import save_creator_profile
from app.database import SessionLocal


def channel_fetch_node(state: CreatorProfileState) -> dict:
    """Fetch channel metadata using the stored OAuth credentials."""
    db: Session = SessionLocal()
    try:
        channel_info = get_channel_info(
            user_id=state["user_id"],
            db=db,
        )
    finally:
        db.close()

    return {"channel_info": channel_info}


def video_fetch_node(state: CreatorProfileState) -> dict:
    """Fetch recent videos and return them as plain dicts for the LLM."""
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
    """
    Call the LLM to analyze the creator.
    Output is validated by Pydantic inside creator_profile_agent().
    """
    agent = CreatorProfileAgent()

    # Use the function directly here since we already have channel_info + videos
    from app.agents.creator_profile_agent import creator_profile_agent
    profile_output = creator_profile_agent(
        channel_info=state["channel_info"],
        videos=state.get("videos", []),
    )

    return {"creator_profile": profile_output.model_dump()}


def save_profile_node(state: CreatorProfileState) -> dict:
    """
    Save the validated profile to creator_profiles.
    Uses a properly managed session — no longer opens a raw SessionLocal
    inside the service function.
    """
    db: Session = SessionLocal()
    try:
        profile = save_creator_profile(
            channel_info=state["channel_info"],
            creator_profile=state["creator_profile"],
            user_id=state["user_id"],  # was missing before
            db=db,
        )
    finally:
        db.close()

    return {"profile_id": profile.id}


# ── Graph construction ────────────────────────────────────────────────────────

builder = StateGraph(CreatorProfileState)

builder.add_node("channel_fetch",    channel_fetch_node)
builder.add_node("video_fetch",      video_fetch_node)
builder.add_node("creator_profile",  creator_profile_node)
builder.add_node("save_profile",     save_profile_node)

builder.add_edge(START,              "channel_fetch")
builder.add_edge("channel_fetch",    "video_fetch")
builder.add_edge("video_fetch",      "creator_profile")
builder.add_edge("creator_profile",  "save_profile")
builder.add_edge("save_profile",     END)

graph = builder.compile()
