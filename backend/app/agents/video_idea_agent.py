from app.services.qwen_service import generate_response
from app.services.model_router import get_model
from app.agents.research_agent import _profile_context
import json, re
from app.agents.utils import load_prompt

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

    prompt_template = load_prompt("video_idea_prompt.txt")

    prompt = prompt_template.format(
        profile_ctx=profile_ctx,
        topic=topic,
        research=research,
        title_style=title_style
    )

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
