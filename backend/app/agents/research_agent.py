from app.services.qwen_service import generate_response
from app.services.model_router import get_model
from app.agents.utils import load_prompt


def _profile_context(creator_profile: dict) -> str:
    """
    Shared personalization context injected into every agent prompt.
    Now includes content_strengths and viral_patterns from MongoDB memory
    (previously these were always [] — now populated from real LLM output).
    """
    if not creator_profile:
        return "No creator profile available."

    audience   = creator_profile.get("audience", {})
    title_style = creator_profile.get("title_style", {})
    desc_style  = creator_profile.get("description_style", {})

    # These now come from MongoDB creator_memory, not hardcoded []
    content_strengths = creator_profile.get("content_strengths", [])
    viral_patterns    = creator_profile.get("viral_patterns", [])

    return f"""
CREATOR PROFILE (use this to personalize your output):
- Niche: {creator_profile.get("creator_niche", creator_profile.get("topics", "General"))}
- Topics: {", ".join(creator_profile.get("main_topics", creator_profile.get("topics", [])))}
- Audience: {audience.get("audience_type", "general audience") if isinstance(audience, dict) else audience}
- Audience Level: {audience.get("audience_level", "beginner") if isinstance(audience, dict) else "beginner"}
- Title Style: {title_style.get("style", "neutral") if isinstance(title_style, dict) else title_style}
- Description Style: {desc_style.get("style", "minimal") if isinstance(desc_style, dict) else desc_style}
- Content Strengths: {", ".join(content_strengths) if content_strengths else "not yet identified"}
- Viral Patterns: {", ".join(viral_patterns) if viral_patterns else "not yet identified"}
""".strip()


def _topic_history_context(topic_history: list[str]) -> str:
    """
    Build the topic history section injected into the research prompt.
    Tells the LLM what topics this creator has already researched
    so it can suggest fresh angles instead of repeating past research.
    """
    if not topic_history:
        return ""
    recent = topic_history[-10:]  # last 10 topics
    items  = "\n".join(f"  - {t}" for t in recent)
    return f"""
PREVIOUSLY RESEARCHED TOPICS (do NOT repeat these — suggest fresh angles):
{items}
""".strip()


def research_agent(
    topic: str,
    plan: str = "normal",
    creator_profile: dict = {},
    topic_history: list[str] = [],
) -> str:
    """
    Research a video topic personalized to the creator's audience.

    New in MCP Phase 1:
      - topic_history: injected to prevent researching already-covered topics
      - content_strengths / viral_patterns now populated from MongoDB memory
    """
    profile_ctx      = _profile_context(creator_profile)
    topic_hist_ctx   = _topic_history_context(topic_history)

    prompt_template  = load_prompt("research.txt")

    # research.txt uses {profile_ctx} and {topic}
    # We append topic_history context after the profile block
    prompt = prompt_template.format(
        profile_ctx=profile_ctx + (f"\n\n{topic_hist_ctx}" if topic_hist_ctx else ""),
        topic=topic,
    )

    model = get_model(plan, "research")
    return generate_response(prompt, model)
