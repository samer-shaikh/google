from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from app.models.plan import Plan
from app.models.user import User
from app.dependencies.auth import get_current_user

from app.agents.script_agent import script_agent

router = APIRouter()


class ScriptRequest(BaseModel):
    topic: str
    research: str
    plan: Plan = Plan.normal
    model: Optional[str] = None  # "gemini" | "qwen" — defaults to DEFAULT_MODEL


@router.post("/script")
def generate_script(
    data: ScriptRequest,
    current_user: User = Depends(get_current_user),
):
    script = script_agent(
        topic=data.topic,
        research=data.research,
        plan=data.plan,
    )

    return {"script": script}
