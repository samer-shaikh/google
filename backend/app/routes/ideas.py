from fastapi import APIRouter,Depends
from pydantic import BaseModel
from app.models.plan import Plan
from app.models.user import User
from app.dependencies.auth import get_current_user

from app.agents.research_agent import research_agent
from app.agents.video_idea_agent import video_idea_agent


router = APIRouter()

class IdeaRequest(BaseModel):
    topic: str
    plan: Plan = Plan.normal


@router.post("/ideas")
def generate_ideas(
    data: IdeaRequest,
     current_user: User = Depends(get_current_user)
     ):

    research = research_agent(
        topic=data.topic,
        plan=data.plan
    )

    ideas = video_idea_agent(
        topic=data.topic,
        research=research,
        plan=data.plan
    )

    return {
        "topic": data.topic,
        "research": research,
        "ideas": ideas
    }