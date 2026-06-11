from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from app.models.plan import Plan
from app.models.user import User
from app.dependencies.auth import get_current_user

from app.agents.research_agent import research_agent
from app.agents.video_idea_agent import video_idea_agent
from app.services.llm_provider import DEFAULT_MODEL

router = APIRouter()


class IdeaRequest(BaseModel):
    topic: str
    plan: Plan = Plan.normal
    model: Optional[str] = None  # "gemini" | "qwen" — defaults to DEFAULT_MODEL


@router.post("/ideas")
def generate_ideas(
    data: IdeaRequest,
    current_user: User = Depends(get_current_user),
):
    # model override: resolve via model_router then pass through llm_provider
    from app.services.model_router import get_model
    resolved_model = data.model or get_model(data.plan, "research")

    research = research_agent(
        topic=data.topic,
        plan=data.plan,
    )

    ideas = video_idea_agent(
        topic=data.topic,
        research=research,
        plan=data.plan,
    )

    return {
        "topic":    data.topic,
        "model":    resolved_model,
        "research": research,
        "ideas":    ideas,
    }
