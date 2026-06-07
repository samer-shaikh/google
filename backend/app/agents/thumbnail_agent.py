from app.services.qwen_service import generate_response
from app.services.model_router import get_model
from app.agents.research_agent import _profile_context
from app.agents.utils import load_prompt

def thumbnail_agent(
    topic: str,
    script: str,
    plan: str = "normal",
    creator_profile: dict = {},
):
    profile_ctx = _profile_context(creator_profile)

    viral_patterns = []
    if creator_profile:
        viral_patterns = creator_profile.get("viral_patterns", [])

    audience = creator_profile.get("audience", {}) if creator_profile else {}
    audience_type = audience.get("audience_type", "general") if isinstance(audience, dict) else "general"

    viral_patterns=", ".join(viral_patterns)
    prompt_template = load_prompt("seo.txt")

    prompt = prompt_template.format(
        profile_ctx=profile_ctx,
        topic=topic,
        script=script,
        audience_type=audience_type,
        viral_patterns=viral_patterns
    )

    model = get_model(plan, "thumbnail")
    return generate_response(prompt, model)
