import json
from app.database import SessionLocal
from sqlalchemy.orm import Session

from app.models.creator_profile import CreatorProfile


def create_profile(
    db: Session,
    channel_id: str,
    channel_name: str,
    topics: list,
    audience: str,
    title_style: dict,
    description_style: dict,
):

    profile = CreatorProfile(
        channel_id=channel_id,
        channel_name=channel_name,
        topics=json.dumps(topics),
        audience=audience,
        title_style=json.dumps(title_style),
        description_style=json.dumps(description_style),
    )

    db.add(profile)
    db.commit()
    db.refresh(profile)

    return profile

def save_creator_profile(
    channel_info: dict,
    creator_profile: dict
):

    db = SessionLocal()

    try:
        
        print(type(creator_profile))
        print(creator_profile)

        profile = CreatorProfile(
            channel_id=channel_info.get("channel_id", "test_channel"),
            channel_name=channel_info["channel_name"],

            topics=creator_profile["main_topics"],

            audience=", ".join(
                creator_profile["audience"]
            ),

            title_style=str(
                creator_profile["title_style"]
            ),

            description_style=str(
                creator_profile["description_style"]
            )
        )

        db.add(profile)

        db.commit()

        db.refresh(profile)

        return profile

    finally:
        db.close()