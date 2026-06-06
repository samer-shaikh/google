"""
upload_record.py — Tracks every YouTube upload attempt.

One row per upload workflow run.
Linked to the Generation that produced the content.
"""
from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base


class UploadRecord(Base):
    __tablename__ = "upload_records"

    id = Column(Integer, primary_key=True)

    # Owner
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Links back to the content generation that was published
    generation_id = Column(
        Integer,
        ForeignKey("generations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # YouTube result
    youtube_video_id  = Column(String, nullable=True, index=True)
    youtube_video_url = Column(Text,   nullable=True)

    # Upload status: pending | uploaded | failed | cancelled
    upload_status = Column(String, default="pending", nullable=False)
    upload_error  = Column(Text, nullable=True)

    # Thumbnail
    thumbnail_status = Column(String, nullable=True)   # uploaded | failed | skipped
    thumbnail_error  = Column(Text,   nullable=True)

    # SEO metadata used at publish time — snapshot so history is accurate
    # even if the user later regenerates SEO
    seo_title       = Column(Text)
    seo_description = Column(Text)
    seo_tags        = Column(JSONB)    # list of strings
    seo_hashtags    = Column(JSONB)    # list of strings
    seo_category    = Column(String)
    privacy_status  = Column(String)

    # Which provider was used (api | mcp)
    provider_used = Column(String, default="api")

    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())
    updated_at   = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
