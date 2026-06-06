from typing import TypedDict, Optional


class AgentState(TypedDict, total=False):
    topic: str
    plan: str

    # main pipeline outputs
    research: str
    script: str
    thumbnail: str
    seo: str

    ideas: list[str]
    selected_idea: str

    # HITL
    human_approved: Optional[bool]


class CreatorProfileState(TypedDict, total=False):
    # user_id was missing — profiles were saved with NULL user_id
    # and could not be linked back to any user
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

    # upload optimizer output
    upload: str
