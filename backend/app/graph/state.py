from typing import TypedDict, Optional


class AgentState(TypedDict, total=False):
    topic: str
    plan: str

    # Creator profile loaded from DB at workflow start
    # All agents use this to personalize their output
    user_id: int
    creator_profile: dict   # full profile dict from creator_profiles table

    # pipeline outputs
    research: str
    script: str
    thumbnail: str
    seo: str

    ideas: list[str]
    selected_idea: str

    # HITL
    human_approved: Optional[bool]


class CreatorProfileState(TypedDict, total=False):
    user_id: int
    channel_id: str
    channel_url: str
    channel_info: dict
    videos: list
    creator_profile: dict
    profile_id: int


class UploadState(TypedDict, total=False):
    topic: str
    plan: str
    script: str
    seo: str
    upload: str
