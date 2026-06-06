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
    # Inputs — passed in when starting the upload workflow
    generation_id: int          # links back to the completed generation
    user_id: int
    plan: str

    # Content pulled from the generation record
    topic: str
    script: str
    thumbnail: str

    # SEO outputs — generated inside this workflow
    seo_title: str
    seo_description: str
    seo_tags: list[str]
    seo_hashtags: list[str]
    seo_category: str

    # Upload metadata — filled by user review or agent suggestion
    privacy_status: str         # "private" | "unlisted" | "public"
    scheduled_at: Optional[str] # ISO datetime string or None

    # Upload results
    youtube_video_id: str       # returned by YouTube API after upload
    upload_status: str          # "pending" | "uploaded" | "failed"
    upload_error: Optional[str]

    # HITL — user reviews SEO + metadata before upload
    seo_approved: Optional[bool]
