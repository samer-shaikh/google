from typing import TypedDict, Optional


class AgentState(TypedDict, total=False):
    topic: str
    plan: str

    # Loaded from DB at workflow start
    user_id: int
    creator_profile: dict   # PostgreSQL profile + MongoDB memory merged

    # Generation record ID
    generation_id: int

    # -- MongoDB memory fields (populated by load_memory_node) -------------
    viral_patterns: list[str]
    content_strengths: list[str]
    successful_hooks: list[str]
    successful_title_patterns: list[str]
    topic_history: list[str]
    audience_intelligence: dict
    content_gaps: list[str]          # from content_gap_agent

    # -- Elastic intelligence fields ----------------------------------------
    trending_topics: list[dict]       # from trend_agent / Elastic
    competitor_insights: list[dict]   # from Elastic competitor_content

    # -- Pipeline outputs ---------------------------------------------------
    research: str
    ideas: list[str]
    selected_idea: str
    script: str
    thumbnail: str

    # -- Critic Agent fields ------------------------------------------------
    script_quality_score: float
    script_critique: str
    script_revision_count: int

    # -- HITL ---------------------------------------------------------------
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
    generation_id: int
    user_id: int
    plan: str
    video_file_path: str
    thumbnail_file_path: str

    topic: str
    script: str
    thumbnail: str

    seo_title: str
    seo_description: str
    seo_tags: list[str]
    seo_hashtags: list[str]
    seo_category: str

    privacy_status: str
    scheduled_at: Optional[str]

    thumbnail_uploaded: bool
    thumbnail_status: str
    thumbnail_error: Optional[str]

    youtube_video_id: str
    youtube_video_url: str
    upload_status: str
    upload_error: Optional[str]

    upload_record_id: int
    provider_used: str
    published_at: Optional[str]

    seo_approved: Optional[bool]
