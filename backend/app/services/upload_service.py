"""
upload_service.py — DB operations for upload history.
All functions accept a db session from the caller — no unmanaged sessions.
"""
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models.upload_record import UploadRecord


def create_upload_record(
    user_id: int,
    generation_id: int,
    seo_title: str,
    seo_description: str,
    seo_tags: list,
    seo_hashtags: list,
    seo_category: str,
    privacy_status: str,
    db: Session,
) -> UploadRecord:
    """Create a pending upload record when the workflow starts uploading."""
    record = UploadRecord(
        user_id=         user_id,
        generation_id=   generation_id,
        upload_status=   "pending",
        seo_title=       seo_title,
        seo_description= seo_description,
        seo_tags=        seo_tags,
        seo_hashtags=    seo_hashtags,
        seo_category=    seo_category,
        privacy_status=  privacy_status,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def complete_upload_record(
    record_id: int,
    youtube_video_id: str,
    youtube_video_url: str,
    thumbnail_status: str,
    provider_used: str,
    db: Session,
    upload_status: str = "uploaded",
) -> UploadRecord:
    """Mark upload complete with YouTube result."""
    db.query(UploadRecord).filter(UploadRecord.id == record_id).update({
        "upload_status":    upload_status,
        "youtube_video_id":  youtube_video_id,
        "youtube_video_url": youtube_video_url,
        "thumbnail_status":  thumbnail_status,
        "provider_used":     provider_used,
        "published_at":      datetime.now(timezone.utc),
    })
    db.commit()
    return db.query(UploadRecord).filter(UploadRecord.id == record_id).first()


def fail_upload_record(
    record_id: int,
    error: str,
    db: Session,
) -> None:
    db.query(UploadRecord).filter(UploadRecord.id == record_id).update({
        "upload_status": "failed",
        "upload_error":  error,
    })
    db.commit()


def cancel_upload_record(record_id: int, db: Session) -> None:
    db.query(UploadRecord).filter(UploadRecord.id == record_id).update({
        "upload_status": "cancelled",
    })
    db.commit()


def get_user_uploads(
    user_id: int,
    db: Session,
    limit: int = 20,
    offset: int = 0,
) -> list[UploadRecord]:
    return (
        db.query(UploadRecord)
        .filter(UploadRecord.user_id == user_id)
        .order_by(UploadRecord.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def get_upload_by_id(
    record_id: int,
    user_id: int,
    db: Session,
) -> UploadRecord | None:
    return (
        db.query(UploadRecord)
        .filter(
            UploadRecord.id == record_id,
            UploadRecord.user_id == user_id,
        )
        .first()
    )
