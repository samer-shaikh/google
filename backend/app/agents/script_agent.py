from app.services.llm_provider import generate_response
from app.services.model_router import get_model
from app.agents.research_agent import _profile_context
from app.agents.utils import load_prompt


def _hooks_context(successful_hooks: list[str]) -> str:
    if not successful_hooks:
        return ""
    recent = successful_hooks[-5:]
    items  = "\n".join(f'  - "{h}"' for h in recent)
    return f"""
HOOKS THAT WORKED FOR THIS CREATOR (use as style reference — do NOT copy verbatim):
{items}
""".strip()


def script_agent(
    topic: str,
    research: str,
    selected_idea: str,
    plan: str = "normal",
    creator_profile: dict = {},
    successful_hooks: list[str] = [],
) -> str:
    profile_ctx = _profile_context(creator_profile)
    hooks_ctx   = _hooks_context(successful_hooks)

    audience = creator_profile.get("audience", {}) if creator_profile else {}
    audience_level = (
        audience.get("audience_level", "beginner")
        if isinstance(audience, dict) else "beginner"
    )
    audience_type = (
        audience.get("audience_type", "general viewers")
        if isinstance(audience, dict) else "general viewers"
    )

    desc_style = creator_profile.get("description_style", {}) if creator_profile else {}
    tone = (
        desc_style.get("style", "conversational")
        if isinstance(desc_style, dict) else "conversational"
    )

    prompt_template = load_prompt("script.txt")

    enriched_profile_ctx = profile_ctx
    if hooks_ctx:
        enriched_profile_ctx = f"{profile_ctx}\n\n{hooks_ctx}"

    prompt = prompt_template.format(
        profile_ctx=enriched_profile_ctx,
        topic=topic,
        research=research,
        audience_type=audience_type,
        audience_level=audience_level,
        tone=tone,
        selected_idea=selected_idea,
    )

    model = get_model(plan, "script")
    return generate_response(prompt, model)
