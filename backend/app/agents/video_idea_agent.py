from app.services.qwen_service import generate_response
from app.services.model_router import get_model
from app.agents.research_agent import _profile_context
from app.agents.utils import load_prompt
import json
import re


def _memory_context(
    past_topics: list[str],
    successful_title_patterns: list[str],
) -> str:
    """
    Build the memory context injected into the idea generation prompt.
    Prevents generating ideas the creator already covered and
    biases idea titles toward proven patterns.
    """
    parts = []

    if past_topics:
        recent = past_topics[-10:]
        items  = "\n".join(f"  - {t}" for t in recent)
        parts.append(
            f"ALREADY COVERED TOPICS (avoid repeating these — suggest different angles):\n{items}"
        )

    if successful_title_patterns:
        items = "\n".join(f"  - {p}" for p in successful_title_patterns[:5])
        parts.append(
            f"TITLE PATTERNS THAT WORKED FOR THIS CREATOR (use these as inspiration):\n{items}"
        )

    return "\n\n".join(parts)


def video_idea_agent(
    topic: str,
    research: str,
    plan: str = "normal",
    creator_profile: dict = {},
    past_topics: list[str] = [],
    successful_title_patterns: list[str] = [],
) -> list[str]:
    """
    Generate 5 personalized video ideas.

    New in MCP Phase 1:
      - past_topics: avoids suggesting ideas the creator already covered
      - successful_title_patterns: biases titles toward proven patterns
      - viral_patterns + content_strengths now populated via creator_profile
    """
    profile_ctx = _profile_context(creator_profile)
    memory_ctx  = _memory_context(past_topics, successful_title_patterns)

    title_style = ""
    if creator_profile:
        ts = creator_profile.get("title_style", {})
        title_style = ts.get("style", "") if isinstance(ts, dict) else str(ts)

    prompt_template = load_prompt("video_idea_prompt.txt")

    # video_idea_prompt.txt uses {profile_ctx}, {topic}, {research}, {title_style}
    # We append memory context to profile_ctx so the template stays unchanged
    enriched_profile_ctx = profile_ctx
    if memory_ctx:
        enriched_profile_ctx = f"{profile_ctx}\n\n{memory_ctx}"

    prompt = prompt_template.format(
        profile_ctx=enriched_profile_ctx,
        topic=topic,
        research=research,
        title_style=title_style,
    )

    print("[video_idea_agent] generating ideas...")
    model = get_model(plan, "video_idea")
    raw   = generate_response(prompt, model)

    # Parse JSON array first
    try:
        cleaned = re.sub(r"```[a-z]*", "", raw).strip().strip("`").strip()
        ideas   = json.loads(cleaned)
        if isinstance(ideas, list) and len(ideas) >= 1:
            return [str(i) for i in ideas[:5]]
    except Exception:
        pass

    # Fallback: numbered / bulleted lines
    lines = [
        re.sub(r"^[\d\-\*\.]+\s*", "", ln).strip()
        for ln in raw.splitlines()
        if ln.strip() and re.match(r"^[\d\-\*]", ln.strip())
    ]
    if lines:
        return lines[:5]

    return [raw.strip()]
