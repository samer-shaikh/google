from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.creator_profile import CreatorProfile
from app.graph.creator_profile_workflow import graph as creator_profile_graph
from app.services.youtube_service import get_channel_info

router = APIRouter(prefix="/creator-profile", tags=["Creator Profile"])


@router.post("/generate")
def generate_creator_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Run the full creator profile workflow:
    1. Fetch channel info from YouTube API
    2. Fetch recent videos from YouTube API
    3. Analyze with LLM
    4. Save to creator_profiles table

    Requires YouTube account to be connected first via /youtube/connect
    """
    result = creator_profile_graph.invoke({
        "user_id": current_user.id,
    })

    return {
        "success": True,
        "profile_id": result.get("profile_id"),
        "channel_info": result.get("channel_info"),
        "creator_profile": result.get("creator_profile"),
    }


@router.get("/me")
def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the current user's saved creator profile."""
    profile = (
        db.query(CreatorProfile)
        .filter(CreatorProfile.user_id == current_user.id)
        .first()
    )

    if not profile:
        raise HTTPException(
            status_code=404,
            detail="No creator profile found. Run POST /creator-profile/generate first.",
        )

    return {
        "id": profile.id,
        "channel_id": profile.channel_id,
        "channel_name": profile.channel_name,
        "topics": profile.topics,
        "audience": profile.audience,
        "title_style": profile.title_style,
        "description_style": profile.description_style,
        "videos_analyzed": profile.videos_analyzed,
        "prompt_version": profile.prompt_version,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }
