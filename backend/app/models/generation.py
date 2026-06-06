from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime

from app.database import Base


class Generation(Base):
    __tablename__ = "generations"

    id = Column(Integer, primary_key=True)

    # Which user owns this generation
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # LangGraph thread_id — links this record to the workflow run
    # so we can look up the full state later if needed
    workflow_thread_id = Column(String, nullable=True, index=True)

    # The topic the user started with
    topic = Column(Text, nullable=False)

    # Plan used (normal / pro / plus)
    plan = Column(String, default="normal")

    # Status: pending → completed / failed
    status = Column(String, default="pending", nullable=False)

    # All workflow outputs stored as JSONB so they're queryable
    # and the schema can evolve without migrations
    research    = Column(Text)
    ideas       = Column(JSONB)          # list of idea strings
    selected_idea = Column(Text)
    script      = Column(Text)
    thumbnail   = Column(Text)
    seo         = Column(Text)

    # The creator profile snapshot used at generation time
    # Stored so you can see WHICH profile version produced this content
    creator_profile_snapshot = Column(JSONB)

    # Error message if status == "failed"
    error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
