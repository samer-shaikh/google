from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from app.models.plan import Plan
from app.models.user import User
from app.dependencies.auth import get_current_user

from app.agents.upload_optimizer_agent import upload_optimizer_agent

router = APIRouter()


class SEORequest(BaseModel):
    topic: str
    script: str
    plan: Plan = Plan.normal
    model: Optional[str] = None  # "gemini" | "qwen" — defaults to DEFAULT_MODEL


@router.post("/seo")
def generate_seo(
    data: SEORequest,
    current_user: User = Depends(get_current_user),
):
    seo = upload_optimizer_agent(
        topic=data.topic,
        script=data.script,
        plan=data.plan,
    )

    return {"seo": seo}
