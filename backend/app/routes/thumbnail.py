from fastapi import APIRouter
from pydantic import BaseModel
from app.models.plan import Plan

from app.agents.thumbnail_agent import thumbnail_agent

router = APIRouter()

class ThumbnailRequest(BaseModel):
    topic: str
    script: str
    plan: Plan = Plan.normal


@router.post("/thumbnail")
def generate_thumbnail(data: ThumbnailRequest):

    thumbnail = thumbnail_agent(
        topic=data.topic,
        script=data.script,
        plan=data.plan
    )

    return {
        "thumbnail": thumbnail
    }