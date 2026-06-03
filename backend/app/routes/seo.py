from fastapi import APIRouter
from pydantic import BaseModel
from app.models.plan import Plan

from app.agents.upload_optimizer_agent import upload_optimizer_agent

router = APIRouter()

class SEORequest(BaseModel):
    topic: str
    script: str
    plan: Plan = Plan.normal


@router.post("/seo")
def generate_seo(data: SEORequest):

    seo = upload_optimizer_agent(
        topic=data.topic,
        script=data.script,
        plan=data.plan
    )

    return {
        "seo": seo
    }