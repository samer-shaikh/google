"""
app/agents/critic_agent.py

Quality gate agent — reviews generated scripts before save_generation_node.
Returns a structured score + critique. If score < threshold, the graph
routes back to script_node with the critique injected into the next prompt.

Score rubric (1-10):
  Hook strength          (0-3) — does the opening compel the viewer to stay?
  Structure clarity      (0-2) — clear intro / body / CTA?
  Audience alignment     (0-2) — matches creator's niche and audience level?
  Originality            (0-2) — avoids generic advice, offers a fresh angle?
  Length appropriateness (0-1) — not too short (<300 words) or bloated (>2000)?

Total: 10. Threshold to pass: 7.
"""
import json
import re
import logging
from app.services.qwen_service import generate_response
from app.services.model_router import get_model

log = logging.getLogger(__name__)

PASS_THRESHOLD = 7
MAX_RETRIES = 2  # max times script_node is re-run before forcing pass


def _build_critic_prompt(
    topic: str,
    selected_idea: str,
    script: str,
    creator_profile: dict,
    revision_count: int,
) -> str:
    niche = creator_profile.get("creator_niche", "General") if creator_profile else "General"
    audience_level = ""
    audience = creator_profile.get("audience", {})
    if isinstance(audience, dict):
        audience_level = audience.get("audience_level", "beginner")

    return f"""
You are a strict YouTube script quality reviewer.

CREATOR NICHE: {niche}
AUDIENCE LEVEL: {audience_level}
TOPIC: {topic}
SELECTED IDEA: {selected_idea}
REVISION NUMBER: {revision_count} (0 = first attempt)

=== SCRIPT TO REVIEW ===
{script[:3000]}
=== END SCRIPT ===

Score this script on the following rubric. Return ONLY a valid JSON object.

{{
  "hook_strength": <integer 0-3>,
  "structure_clarity": <integer 0-2>,
  "audience_alignment": <integer 0-2>,
  "originality": <integer 0-2>,
  "length_appropriateness": <integer 0-1>,
  "total_score": <integer 0-10>,
  "passed": <true if total_score >= 7, else false>,
  "critique": "<2-3 sentences of specific, actionable feedback for the script writer>",
  "strongest_element": "<what works best>",
  "weakest_element": "<what needs the most improvement>"
}}

Be strict. A score of 7+ means this script is ready to publish without changes.
Return ONLY the JSON. No markdown. No preamble.
""".strip()


def critic_agent(
    topic: str,
    selected_idea: str,
    script: str,
    plan: str = "normal",
    creator_profile: dict = {},
    revision_count: int = 0,
) -> dict:
    """
    Review a generated script and return a structured quality report.

    Returns:
        {
            "passed": bool,
            "total_score": int,
            "critique": str,
            "strongest_element": str,
            "weakest_element": str,
            "hook_strength": int,
            "structure_clarity": int,
            "audience_alignment": int,
            "originality": int,
            "length_appropriateness": int,
        }

    Always returns a dict — never raises. On LLM/parse failure, returns
    a default pass=True so the workflow is never stuck.
    """
    # If max retries reached, force pass to avoid infinite loops
    if revision_count >= MAX_RETRIES:
        log.info(f"[critic_agent] max retries ({MAX_RETRIES}) reached — forcing pass")
        return {
            "passed": True,
            "total_score": 7,
            "critique": "Maximum revision limit reached — passing script as-is.",
            "strongest_element": "N/A",
            "weakest_element": "N/A",
            "hook_strength": 2,
            "structure_clarity": 2,
            "audience_alignment": 1,
            "originality": 1,
            "length_appropriateness": 1,
        }

    prompt = _build_critic_prompt(
        topic=topic,
        selected_idea=selected_idea,
        script=script,
        creator_profile=creator_profile,
        revision_count=revision_count,
    )

    try:
        model = get_model(plan, "research")  # use fast model for critic
        raw = generate_response(prompt, model)
        cleaned = re.sub(r"```[a-z]*", "", raw).strip().strip("`").strip()
        result = json.loads(cleaned)

        # Ensure required keys exist with safe defaults
        result.setdefault("passed", result.get("total_score", 0) >= PASS_THRESHOLD)
        result.setdefault("total_score", 0)
        result.setdefault("critique", "No critique provided.")
        result.setdefault("strongest_element", "")
        result.setdefault("weakest_element", "")

        log.info(
            f"[critic_agent] score={result['total_score']}/10 "
            f"passed={result['passed']} revision={revision_count}"
        )
        print(
            f"[critic_agent] score={result['total_score']}/10 | "
            f"passed={result['passed']} | {result.get('weakest_element', '')}"
        )
        return result

    except Exception as e:
        log.warning(f"[critic_agent] failed to parse critique — forcing pass: {e}")
        return {
            "passed": True,
            "total_score": 7,
            "critique": f"Critic parse error ({e}) — passing script.",
            "strongest_element": "",
            "weakest_element": "",
            "hook_strength": 2,
            "structure_clarity": 2,
            "audience_alignment": 1,
            "originality": 1,
            "length_appropriateness": 1,
        }
