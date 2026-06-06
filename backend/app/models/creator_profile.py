from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database import Base


class CreatorProfile(Base):
    __tablename__ = "creator_profiles"

    id = Column(Integer, primary_key=True, index=True)

    # Fixed: was String — must match users.id which is Integer
    # Fixed: was nullable=True with no FK — now properly linked to users table
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    channel_id = Column(String, nullable=False, index=True)
    channel_name = Column(String, nullable=False)

    # JSONB fields — store structured LLM output
    topics = Column(JSONB)
    audience = Column(JSONB)
    title_style = Column(JSONB)
    description_style = Column(JSONB)

    # Track how many videos were used to build this profile
    videos_analyzed = Column(Integer, default=0)

    # Prompt version — bump this when you change the LLM prompt so you
    # know which profiles need to be regenerated
    prompt_version = Column(String, default="v1")

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
