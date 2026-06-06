from app.services.qwen_service import generate_response
from app.services.model_router import get_model


def _profile_context(creator_profile: dict) -> str:
    """
    Convert the creator profile dict into a compact context string
    injected into every agent prompt so output is personalized.
    """
    if not creator_profile:
        return "No creator profile available."

    audience = creator_profile.get("audience", {})
    title_style = creator_profile.get("title_style", {})
    desc_style = creator_profile.get("description_style", {})

    return f"""
CREATOR PROFILE (use this to personalize your output):
- Niche: {creator_profile.get("creator_niche", creator_profile.get("topics", "General"))}
- Topics: {", ".join(creator_profile.get("main_topics", creator_profile.get("topics", [])))}
- Audience: {audience.get("audience_type", "general audience")}
- Audience Level: {audience.get("audience_level", "beginner")}
- Title Style: {title_style.get("style", "neutral")}
- Description Style: {desc_style.get("style", "minimal")}
- Content Strengths: {", ".join(creator_profile.get("content_strengths", []))}
- Viral Patterns: {", ".join(creator_profile.get("viral_patterns", []))}
""".strip()


def research_agent(
    topic: str,
    plan: str = "normal",
    creator_profile: dict = {},
) -> str:

    profile_ctx = _profile_context(creator_profile)

    prompt = f"""
You are a YouTube research expert helping a specific creator.

{profile_ctx}

Research this topic for the creator above. Tailor insights to their audience level and niche.

Topic: {topic}

Return:
1. Main ideas relevant to this creator's audience
2. Trending angles that match their content style
3. Audience pain points specific to their viewers
4. Viral opportunities that fit their channel
"""

    model = get_model(plan, "research")
    return generate_response(prompt, model)
