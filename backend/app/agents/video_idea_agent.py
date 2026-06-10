from app.services.qwen_service import generate_response
from app.services.model_router import get_model
from app.agents.research_agent import _profile_context
from app.agents.utils import load_prompt
import asyncio
import logging
import json
import re

log = logging.getLogger(__name__)


def _try_mcp_creator_memory(user_id: int, past_topics: list[str], title_patterns: list[str]):
    """
    Attempt to enrich past_topics and title_patterns via MongoDB MCP.
    Returns (past_topics, title_patterns) — falls back to originals if MCP unavailable.
    Never raises.
    """
    if not user_id:
        return past_topics, title_patterns
    try:
        from app.mcp.mongodb.mcp_runner import call_mcp_tool
        import concurrent.futures

        async def _fetch():
            doc = await call_mcp_tool("find", {
                "collection": "creator_memory",
                "filter": {"user_id": user_id},
                "limit": 1,
                "projection": {"topic_history": 1, "successful_title_patterns": 1},
            })
            if doc and isinstance(doc, list) and len(doc) > 0:
                return doc[0]
            return None

        # Run in a fresh thread to avoid deadlocking inside LangGraph's event loop
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, _fetch())
            mem_doc = future.result(timeout=8.0)

        if mem_doc:
            mcp_topics = mem_doc.get("topic_history", [])
            mcp_patterns = mem_doc.get("successful_title_patterns", [])
            merged_topics = list(dict.fromkeys(mcp_topics + past_topics))
            merged_patterns = list(dict.fromkeys(mcp_patterns + title_patterns))
            log.info(
                f"[video_idea_agent] MCP memory: {len(merged_topics)} topics, "
                f"{len(merged_patterns)} title patterns"
            )
            return merged_topics, merged_patterns
    except Exception as e:
        log.debug(f"[video_idea_agent] MCP memory fetch skipped: {e}")
    return past_topics, title_patterns


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
    user_id = creator_profile.get("user_id") if creator_profile else None
    past_topics, successful_title_patterns = _try_mcp_creator_memory(
        user_id, past_topics, successful_title_patterns
    )

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
