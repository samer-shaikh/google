"""
profile_service.py

Previously save_creator_profile() opened its own SessionLocal() directly,
bypassing FastAPI's dependency injection and creating unmanaged sessions
that could leak under load.

Fix: All functions now accept a db: Session parameter — the caller
(route or workflow node) is responsible for passing the session.
The workflow node passes a session it opens and closes itself.
"""
from sqlalchemy.orm import Session

from app.models.creator_profile import CreatorProfile


def get_profile_by_user(user_id: int, db: Session) -> CreatorProfile | None:
    return (
        db.query(CreatorProfile)
        .filter(CreatorProfile.user_id == user_id)
        .first()
    )


def get_profile_by_channel(channel_id: str, db: Session) -> CreatorProfile | None:
    return (
        db.query(CreatorProfile)
        .filter(CreatorProfile.channel_id == channel_id)
        .first()
    )


def save_creator_profile(
    channel_info: dict,
    creator_profile: dict,
    user_id: int,
    db: Session,
) -> CreatorProfile:
    """
    Upsert a creator profile row.

    Args:
        channel_info:    Dict with channel_id, channel_name
        creator_profile: Validated dict (from CreatorProfileOutput.model_dump())
        user_id:         Integer FK to users.id  (was missing before — profiles had NULL user_id)
        db:              Injected SQLAlchemy session (no longer opens its own)
    """
    existing = (
        db.query(CreatorProfile)
        .filter(
            CreatorProfile.user_id == user_id,
            CreatorProfile.channel_id == channel_info.get("channel_id", ""),
        )
        .first()
    )

    if existing:
        existing.channel_name = channel_info.get("channel_name", existing.channel_name)
        existing.topics = creator_profile.get("main_topics", existing.topics)
        existing.audience = {
            "audience_type": creator_profile.get("audience_type", ""),
            "audience_level": creator_profile.get("audience_level", ""),
        }
        existing.title_style = {"style": creator_profile.get("title_style", "")}
        existing.description_style = {"style": creator_profile.get("description_style", "")}
        profile = existing
    else:
        profile = CreatorProfile(
            user_id=user_id,
            channel_id=channel_info.get("channel_id", ""),
            channel_name=channel_info.get("channel_name", ""),
            topics=creator_profile.get("main_topics", []),
            audience={
                "audience_type": creator_profile.get("audience_type", ""),
                "audience_level": creator_profile.get("audience_level", ""),
            },
            title_style={"style": creator_profile.get("title_style", "")},
            description_style={"style": creator_profile.get("description_style", "")},
        )
        db.add(profile)

    db.commit()
    db.refresh(profile)
    return profile
