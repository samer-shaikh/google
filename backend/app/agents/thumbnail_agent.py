from app.services.qwen_service import generate_response
from app.services.model_router import get_model
from app.agents.research_agent import _profile_context


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

    prompt = f"""
You are a YouTube thumbnail expert working for a specific creator.

{profile_ctx}

Topic: {topic}

Script:
{script}

This creator's viral patterns: {", ".join(viral_patterns) if viral_patterns else "not specified"}
Target audience: {audience_type}

Design a thumbnail that fits this creator's channel style and will appeal to their specific audience.

Generate:
1. Thumbnail Text — short, punchy, matches creator's title style
2. Thumbnail Concept — visual description tailored to their audience
3. Emotion — the emotion this thumbnail should trigger in their viewers
4. Color Suggestions — colors that match their channel brand/niche
5. Thumbnail Prompt — detailed AI image generation prompt for this specific creator

Return in markdown.
"""

    model = get_model(plan, "thumbnail")
    return generate_response(prompt, model)
