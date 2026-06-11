from app.services.llm_provider import generate_response
from app.services.model_router import get_model
from app.agents.research_agent import _profile_context
from app.agents.utils import load_prompt


def seo_agent(
    topic: str,
    script: str,
    plan: str = "normal",
    creator_profile: dict = {},
):
    profile_ctx = _profile_context(creator_profile)

    main_topics = []
    if creator_profile:
        raw = creator_profile.get("main_topics", creator_profile.get("topics", []))
        main_topics = raw if isinstance(raw, list) else []

    audience = creator_profile.get("audience", {}) if creator_profile else {}
    audience_type = audience.get("audience_type", "") if isinstance(audience, dict) else ""

    prompt_template = load_prompt("seo.txt")
    main_topics_str = ", ".join(main_topics)

    prompt = prompt_template.format(
        profile_ctx=profile_ctx,
        topic=topic,
        script=script,
        audience_type=audience_type,
        main_topics=main_topics_str,
    )

    model = get_model(plan, "seo")
    return generate_response(prompt, model)
