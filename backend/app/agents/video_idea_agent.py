from app.services.qwen_service import generate_response
from app.services.model_router import get_model
from app.agents.research_agent import _profile_context
import json, re


def video_idea_agent(
    topic: str,
    research: str,
    plan: str = "normal",
    creator_profile: dict = {},
):
    profile_ctx = _profile_context(creator_profile)

    # Extract title style so ideas match the creator's existing pattern
    title_style = ""
    if creator_profile:
        ts = creator_profile.get("title_style", {})
        title_style = ts.get("style", "") if isinstance(ts, dict) else str(ts)

    prompt = f"""
You are a YouTube strategist working for a specific creator.

{profile_ctx}

Topic: {topic}

Research:
{research}

Generate exactly 5 viral video ideas personalized for this creator.
Match their title style: "{title_style}"
Make ideas fit their audience level and niche — not generic YouTube advice.

Return ONLY a JSON array of exactly 5 strings. No markdown, no explanation, no preamble.
Each string is one complete video idea title + one sentence description.

Example format:
["Idea one title — one sentence why it works", "Idea two — one sentence", "Idea three — one sentence", "Idea four — one sentence", "Idea five — one sentence"]
"""

    print("video ideas agent start working...")
    model = get_model(plan, "video_idea")
    raw = generate_response(prompt, model)

    try:
        cleaned = re.sub(r"```[a-z]*", "", raw).strip().strip("`").strip()
        ideas = json.loads(cleaned)
        if isinstance(ideas, list) and len(ideas) >= 1:
            return [str(i) for i in ideas[:5]]
    except Exception:
        pass

    lines = [
        re.sub(r"^[\d\-\*\.]+\s*", "", ln).strip()
        for ln in raw.splitlines()
        if ln.strip() and re.match(r"^[\d\-\*]", ln.strip())
    ]
    if lines:
        return lines[:5]

    return [raw.strip()]
