from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from datetime import datetime

from app.database import Base


class YouTubeAccount(Base):
    __tablename__ = "youtube_accounts"

    id = Column(Integer, primary_key=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,   # one YouTube account per user
        index=True,
    )

    channel_id = Column(String, index=True)
    channel_name = Column(String)

    # Tokens — must be encrypted at rest in production (e.g. via pgcrypto)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text)

    # Now properly populated in the OAuth callback
    token_expiry = Column(DateTime)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
