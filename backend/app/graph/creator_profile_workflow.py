from langgraph.graph import StateGraph,START,END
from app.services.youtube_service import get_channel_info, get_recent_videos
from app.agents.creator_profile_agent import creator_profile_agent
from app.graph.state import CreatorProfileState
from app.services.profile_service import (
    save_creator_profile
)

def channel_fetch_node(state: CreatorProfileState):

    channel_info = get_channel_info(
        state["channel_url"]
    )

    return {
        "channel_info": channel_info
    }


def video_fetch_node(state: CreatorProfileState):

    videos = get_recent_videos(
        state["channel_url"]
    )

    return {
        "videos": videos
    }


def creator_profile_node(state: CreatorProfileState):

    profile = creator_profile_agent(
        state["channel_info"],
        state["videos"]
    )

    return {
        "creator_profile": profile
    }


def save_profile_node(state):

    profile = save_creator_profile(
        state["channel_info"],
        state["creator_profile"]
    )

    return {
        "profile_id": profile.id
    }

builder = StateGraph(CreatorProfileState)

builder.add_node(
    "channel_fetch",
    channel_fetch_node
)

builder.add_node(
    "video_fetch",
    video_fetch_node
)

builder.add_node(
    "creator_profile",
    creator_profile_node
)

builder.add_node(
    "save_profile",
    save_profile_node
)

builder.add_edge(
    START,
    "channel_fetch"
)

builder.add_edge(
    "channel_fetch",
    "video_fetch"
)

builder.add_edge(
    "video_fetch",
    "creator_profile"
)

builder.add_edge(
    "creator_profile",
    "save_profile"
)

builder.add_edge(
    "save_profile",
    END
)

graph = builder.compile()