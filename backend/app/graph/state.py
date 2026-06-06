from typing import TypedDict, Optional


# ── Content Generation Workflow State ────────────────────────────
# Research → Ideas → Script → Thumbnail → Save
# SEO is NOT part of this workflow — it belongs in the Upload Workflow.

class AgentState(TypedDict, total=False):
    topic: str
    plan: str

    # Loaded from DB at workflow start
    user_id: int
    creator_profile: dict

    # Generation record ID — created at /workflow/run, updated throughout
    generation_id: int

    # Pipeline outputs
    research: str
    ideas: list[str]
    selected_idea: str
    script: str
    thumbnail: str          # thumbnail concept/prompt from ThumbnailAgent

    # HITL
    human_approved: Optional[bool]


# ── Creator Profile Workflow State ───────────────────────────────

class CreatorProfileState(TypedDict, total=False):
    user_id: int
    channel_id: str
    channel_url: str
    channel_info: dict
    videos: list
    creator_profile: dict
    profile_id: int


# ── Upload / Publishing Workflow State ───────────────────────────
# Dedicated to the separate publishing pipeline.
# SEO generation lives here, not in the content generation workflow.

class UploadState(TypedDict, total=False):
    # Inputs
    generation_id: int
    user_id: int
    plan: str

    # Content pulled from the generation record
    topic: str
    script: str
    thumbnail: str

    # Video file path — provided by the user when starting the upload workflow
    # Must be an absolute path to a .mp4 / .mov file on the server
    video_file_path: str

    # SEO outputs
    seo_title: str
    seo_description: str
    seo_tags: list[str]
    seo_hashtags: list[str]
    seo_category: str

    # Upload metadata
    privacy_status: str
    scheduled_at: Optional[str]

    # Thumbnail upload result
    thumbnail_uploaded: bool
    thumbnail_status: str       # "uploaded" | "failed" | "skipped"
    thumbnail_error: Optional[str]

    # Video upload result
    youtube_video_id: str
    youtube_video_url: str
    upload_status: str          # "pending" | "uploaded" | "failed" | "cancelled"
    upload_error: Optional[str]

    # Upload record ID — created before upload, updated after
    upload_record_id: int

    # Which provider was used
    provider_used: str          # "api" | "mcp"

    # Published timestamp
    published_at: Optional[str]

    # HITL
    seo_approved: Optional[bool]
