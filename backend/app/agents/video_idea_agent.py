from app.services.qwen_service import generate_response
from app.services.model_router import get_model
import json, re

def video_idea_agent(topic: str, research: str, plan: str = "normal"):

    prompt = f"""
You are a YouTube strategist.

Topic:
{topic}

Research:
{research}

Generate exactly 5 viral video ideas for this topic.

Return ONLY a JSON array of exactly 5 strings. No markdown, no explanation, no preamble.
Each string is one complete video idea title + one sentence description.

Example format:
["Idea one title — one sentence why it works", "Idea two title — one sentence why it works", "Idea three title — one sentence why it works", "Idea four title — one sentence why it works", "Idea five title — one sentence why it works"]
"""

    print("video ideas agent start working ...")
    model = get_model(plan, "video_idea")
    raw = generate_response(prompt, model)

    # Try to parse as JSON list
    try:
        # Strip markdown code fences if the LLM wraps it
        cleaned = re.sub(r"```[a-z]*", "", raw).strip().strip("`").strip()
        ideas = json.loads(cleaned)
        if isinstance(ideas, list) and len(ideas) >= 1:
            return [str(i) for i in ideas[:5]]
    except Exception:
        pass

    # Fallback: split on numbered lines  "1. ..." or "- ..."
    lines = [
        re.sub(r"^[\d\-\*\.]+\s*", "", ln).strip()
        for ln in raw.splitlines()
        if ln.strip() and re.match(r"^[\d\-\*]", ln.strip())
    ]
    if lines:
        return lines[:5]

    # Last resort: return the raw text as one item so nothing breaks
    return [raw.strip()]
