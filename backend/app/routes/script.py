from fastapi import APIRouter
from pydantic import BaseModel
from app.models.plan import Plan
from app.models.user import User
from app.dependencies.auth import get_current_user

from app.agents.script_agent import script_agent

router = APIRouter()

class ScriptRequest(BaseModel):
    topic: str
    research: str
    plan: Plan = Plan.normal


@router.post("/script")
def generate_script(data: ScriptRequest):

    script = script_agent(
        topic=data.topic,
        research=data.research,
        plan=data.plan
    )

    return {
        "script": script
    }