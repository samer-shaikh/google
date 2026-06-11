from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from app.models.plan import Plan
from app.models.user import User
from app.dependencies.auth import get_current_user

from app.agents.thumbnail_agent import thumbnail_agent

router = APIRouter()


class ThumbnailRequest(BaseModel):
    topic: str
    script: str
    plan: Plan = Plan.normal
    model: Optional[str] = None  # "gemini" | "qwen" — defaults to DEFAULT_MODEL


@router.post("/thumbnail")
def generate_thumbnail(
    data: ThumbnailRequest,
    current_user: User = Depends(get_current_user),
):
    thumbnail = thumbnail_agent(
        topic=data.topic,
        script=data.script,
        plan=data.plan,
    )

    return {"thumbnail": thumbnail}
