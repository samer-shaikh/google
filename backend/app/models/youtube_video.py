from sqlalchemy import Column, Integer, String, Text, BigInteger, DateTime, Boolean, ForeignKey
from sqlalchemy.sql import func
from datetime import datetime

from app.database import Base


class YouTubeVideo(Base):
    __tablename__ = "youtube_videos"

    id = Column(Integer, primary_key=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # YouTube's own video ID — unique constraint prevents duplicate inserts
    # on re-fetch / retry runs
    video_id = Column(String, unique=True, nullable=False, index=True)

    title = Column(Text)
    description = Column(Text)

    views = Column(BigInteger, default=0)
    likes = Column(BigInteger, default=0)
    comments = Column(BigInteger, default=0)

    published_at = Column(DateTime)

    # When we fetched this row — lets us do incremental syncs
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())

    # Flip to True after CreatorProfileAgent has processed this video
    # so we can skip already-analyzed videos on subsequent runs
    is_analyzed = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)
