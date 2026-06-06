from app.services.qwen_service import generate_response
from app.services.model_router import get_model
from app.agents.research_agent import _profile_context


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

    prompt = f"""
You are an expert YouTube script writer working for a specific creator.

{profile_ctx}

Original Topic: {topic}
Selected Video Idea: {selected_idea}

Research:
{research}

Write a complete YouTube script tailored to:
- Audience: {audience_type}
- Level: {audience_level} — adjust complexity and vocabulary accordingly
- Tone: {tone}

Requirements:
- Strong hook in first 15 seconds that grabs THIS creator's specific audience
- Clear introduction that matches their channel style
- Main content with multiple sections at the right complexity level
- Real examples that resonate with this audience
- Conversational tone matching the creator's style
- Strong CTA at the end

Format:
# Hook
# Introduction
# Main Content
# Conclusion
# Call To Action

Make the script detailed, engaging, and optimized for this creator's specific audience.
"""

    model = get_model(plan, "script")
    return generate_response(prompt, model)
