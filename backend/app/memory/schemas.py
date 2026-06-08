"""
app/memory/schemas.py

Pydantic schemas for all MongoDB memory documents.

These are NOT SQLAlchemy models. They describe the shape of documents
stored in MongoDB collections. Using Pydantic here provides:
  - Validation before writing to MongoDB
  - Type-safe reads from MongoDB
  - Clear documentation of the memory schema

Collections:
  - CreatorMemoryDocument   → creator_memory collection
  - ResearchSessionDocument → research_sessions collection
  - ContentPieceDocument    → content_pieces collection
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Creator Memory ────────────────────────────────────────────────────────────

class AudienceIntelligence(BaseModel):
    """Accumulated knowledge about what the creator's audience cares about."""
    common_questions: list[str] = Field(default_factory=list)
    content_gaps: list[str] = Field(default_factory=list)
    frustrations: list[str] = Field(default_factory=list)
    recurring_themes: list[str] = Field(default_factory=list)


class PerformanceSummary(BaseModel):
    """Aggregated performance signals (populated when YouTube analytics available)."""
    avg_views_last_10: int = 0
    best_performing_topic: Optional[str] = None
    best_performing_format: Optional[str] = None
    avg_engagement_rate: float = 0.0
    total_videos_generated: int = 0
    total_videos_uploaded: int = 0


class CreatorMemoryProfile(BaseModel):
    """
    The profile section of creator_memory.
    Mirrors CreatorProfileOutput fields but is enriched over time.
    """
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
    Root document for creator_memory collection.
    One document per user. Updated incrementally across every workflow run.

    MongoDB collection: creator_memory
    Primary key: user_id (unique index)
    """
    user_id: int
    channel_id: str = ""
    channel_name: str = ""
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    # Core profile — synced from PostgreSQL creator_profiles on every run
    profile: CreatorMemoryProfile = Field(default_factory=CreatorMemoryProfile)

    # ── Fields that were always [] in the old system ──────────────
    # These are now populated from LLM output and accumulated over time.
    content_strengths: list[str] = Field(default_factory=list)
    viral_patterns: list[str] = Field(default_factory=list)
    recommended_video_types: list[str] = Field(default_factory=list)

    # ── Accumulated learning across runs ──────────────────────────
    topic_history: list[str] = Field(
        default_factory=list,
        description="All topics researched so far — used to avoid repetition"
    )
    successful_hooks: list[str] = Field(
        default_factory=list,
        description="Opening lines that the creator approved and used"
    )
    successful_title_patterns: list[str] = Field(
        default_factory=list,
        description="Title patterns that matched creator's style (e.g. 'Learn X Like Y')"
    )

    # ── Audience intelligence ─────────────────────────────────────
    audience_intelligence: AudienceIntelligence = Field(
        default_factory=AudienceIntelligence
    )

    # ── Performance signals ───────────────────────────────────────
    performance_summary: PerformanceSummary = Field(
        default_factory=PerformanceSummary
    )

    def to_mongo(self) -> dict:
        """Convert to dict for MongoDB insert/update. Excludes None values."""
        return self.model_dump(exclude_none=True)

    @classmethod
    def from_mongo(cls, doc: dict) -> "CreatorMemoryDocument":
        """Build from a MongoDB document dict."""
        doc.pop("_id", None)  # remove MongoDB _id before Pydantic validation
        return cls(**doc)


# ── Research Session ──────────────────────────────────────────────────────────

class ResearchSessionDocument(BaseModel):
    """
    One document per research workflow run.

    MongoDB collection: research_sessions
    """
    user_id: int
    generation_id: int
    topic: str
    created_at: datetime = Field(default_factory=_now)

    # Full research output from ResearchAgent
    research_output: str = ""

    # Structured extractions (filled by ResearchAgent after LLM call)
    key_insights: list[str] = Field(default_factory=list)
    pain_points_identified: list[str] = Field(default_factory=list)
    trending_angles: list[str] = Field(default_factory=list)

    # Downstream outcomes (filled by IdeaAgent and user selection)
    ideas_generated: int = 0
    idea_selected: Optional[str] = None

    def to_mongo(self) -> dict:
        return self.model_dump(exclude_none=True)


# ── Content Piece ─────────────────────────────────────────────────────────────

class ContentSEO(BaseModel):
    title: str = ""
    tags: list[str] = Field(default_factory=list)
    category: str = ""


class ContentPieceDocument(BaseModel):
    """
    One document per completed generation.
    Created by save_generation_node after the full content workflow completes.

    MongoDB collection: content_pieces
    """
    user_id: int
    generation_id: int
    topic: str
    created_at: datetime = Field(default_factory=_now)

    # Selected content
    selected_idea: str = ""
    script_word_count: int = 0
    thumbnail_concept: str = ""

    # SEO snapshot (filled after upload workflow)
    seo: ContentSEO = Field(default_factory=ContentSEO)

    # YouTube result (filled after successful upload)
    youtube_video_id: Optional[str] = None
    upload_record_id: Optional[int] = None

    def to_mongo(self) -> dict:
        return self.model_dump(exclude_none=True)
