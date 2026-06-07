from app.services.qwen_service import generate_response
from app.services.model_router import get_model
from app.agents.research_agent import _profile_context
from app.agents.utils import load_prompt

def script_agent(
    topic: str,
    research: str,
    selected_idea: str,
    plan: str = "normal",
    creator_profile: dict = {},
):
    profile_ctx = _profile_context(creator_profile)

    audience = creator_profile.get("audience", {}) if creator_profile else {}
    audience_level = audience.get("audience_level", "beginner") if isinstance(audience, dict) else "beginner"
    audience_type  = audience.get("audience_type", "general viewers") if isinstance(audience, dict) else "general viewers"

    desc_style = creator_profile.get("description_style", {}) if creator_profile else {}
    tone = desc_style.get("style", "conversational") if isinstance(desc_style, dict) else "conversational"

    prompt_template = load_prompt("script.txt")

    prompt = prompt_template.format(
        profile_ctx=profile_ctx,
        topic=topic
    )

    model = get_model(plan, "script")
    return generate_response(prompt, model)
