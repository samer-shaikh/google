"""
app/mcp/mongodb/schemas.py

Pydantic schemas for all MongoDB memory documents.
Used for validation before writes and type-safe reads.
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AudienceIntelligence(BaseModel):
    common_questions: list[str] = Field(default_factory=list)
    content_gaps: list[str] = Field(default_factory=list)
    frustrations: list[str] = Field(default_factory=list)
    recurring_themes: list[str] = Field(default_factory=list)


class PerformanceSummary(BaseModel):
    avg_views_last_10: int = 0
    best_performing_topic: Optional[str] = None
    best_performing_format: Optional[str] = None
    avg_engagement_rate: float = 0.0
    total_videos_generated: int = 0
    total_videos_uploaded: int = 0


class CreatorMemoryProfile(BaseModel):
    niche: str = ""
    main_topics: list[str] = Field(default_factory=list)
    audience_type: str = ""
    audience_level: str = "beginner"
    content_goals: list[str] = Field(default_factory=list)
    preferred_tone: str = ""
    title_style: str = ""
    description_style: str = ""
    prompt_version: str = "v1"


class CreatorMemoryDocument(BaseModel):
    """
    Root document — one per user.
    MongoDB collection: creator_memory
    """
    user_id: int
    channel_id: str = ""
    channel_name: str = ""
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    profile: CreatorMemoryProfile = Field(default_factory=CreatorMemoryProfile)

    # Previously always [] — now populated from LLM output
    content_strengths: list[str] = Field(default_factory=list)
    viral_patterns: list[str] = Field(default_factory=list)
    recommended_video_types: list[str] = Field(default_factory=list)

    # Accumulated learning
    topic_history: list[str] = Field(default_factory=list)
    successful_hooks: list[str] = Field(default_factory=list)
    successful_title_patterns: list[str] = Field(default_factory=list)

    # Audience intelligence
    audience_intelligence: AudienceIntelligence = Field(
        default_factory=AudienceIntelligence
    )

    performance_summary: PerformanceSummary = Field(
        default_factory=PerformanceSummary
    )

    def to_mongo(self) -> dict:
        return self.model_dump(exclude_none=True)

    @classmethod
    def from_mongo(cls, doc: dict) -> "CreatorMemoryDocument":
        doc.pop("_id", None)
        return cls(**doc)


class ResearchSessionDocument(BaseModel):
    """
    One document per research workflow run.
    MongoDB collection: research_sessions
    """
    user_id: int
    generation_id: int
    topic: str
    created_at: datetime = Field(default_factory=_now)
    research_output: str = ""
    key_insights: list[str] = Field(default_factory=list)
    pain_points_identified: list[str] = Field(default_factory=list)
    trending_angles: list[str] = Field(default_factory=list)
    hook_ideas: list[str] = Field(default_factory=list)
    ideas_generated: int = 0
    idea_selected: Optional[str] = None

    def to_mongo(self) -> dict:
        return self.model_dump(exclude_none=True)


class ContentPieceSEO(BaseModel):
    title: str = ""
    tags: list[str] = Field(default_factory=list)
    category: str = ""


class ContentPieceDocument(BaseModel):
    """
    One document per completed generation.
    MongoDB collection: content_pieces
    """
    user_id: int
    generation_id: int
    topic: str
    created_at: datetime = Field(default_factory=_now)
    selected_idea: str = ""
    script_word_count: int = 0
    script_hook: str = ""
    thumbnail_concept: str = ""
    seo: ContentPieceSEO = Field(default_factory=ContentPieceSEO)
    youtube_video_id: Optional[str] = None
    upload_record_id: Optional[int] = None

    def to_mongo(self) -> dict:
        return self.model_dump(exclude_none=True)
