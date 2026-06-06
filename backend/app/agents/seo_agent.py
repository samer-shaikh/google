from app.services.qwen_service import generate_response
from app.services.model_router import get_model
from app.agents.research_agent import _profile_context


def seo_agent(
    topic: str,
    script: str,
    plan: str = "normal",
    creator_profile: dict = {},
):
    profile_ctx = _profile_context(creator_profile)

    # Pull main topics for tag suggestions
    main_topics = []
    if creator_profile:
        raw = creator_profile.get("main_topics", creator_profile.get("topics", []))
        main_topics = raw if isinstance(raw, list) else []

    audience = creator_profile.get("audience", {}) if creator_profile else {}
    audience_type = audience.get("audience_type", "") if isinstance(audience, dict) else ""

    prompt = f"""
You are a YouTube SEO expert working for a specific creator.

{profile_ctx}

Topic: {topic}

Script:
{script}

Generate SEO optimized for this creator's channel and audience ({audience_type}).
Include their main topics ({", ".join(main_topics)}) naturally in tags and description.

Generate:
1. SEO Title — match the creator's title style, optimized for search
2. Description — 150-200 words, matches their description style
3. 15 Tags — mix of broad and niche tags relevant to their channel topics
4. 10 Hashtags — relevant to their niche

Return in clean markdown.
"""

    model = get_model(plan, "seo")
    return generate_response(prompt, model)
