from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.dialects.postgresql import JSONB    
from sqlalchemy.sql import func

from app.database import Base


class CreatorProfile(Base):
    __tablename__ = "creator_profiles"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(String, nullable=True)

    channel_id = Column(String, unique=True, nullable=False)
    channel_name = Column(String, nullable=False)

    topics = Column(JSONB)
    
    audience = Column(JSONB)

    title_style = Column(JSONB)

    description_style = Column(JSONB)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )