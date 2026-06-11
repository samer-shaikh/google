"""
app/agents/content_gap_agent.py

Content opportunity finder.
Analyses MongoDB topic_history + Elastic competitor/audience data
to surface topics the creator hasn't covered yet.
"""
import json
import re
import logging
from typing import Optional
from app.services.llm_provider import generate_response
from app.services.model_router import get_model

log = logging.getLogger(__name__)


def _fetch_topic_history(user_id: int) -> list[str]:
    import asyncio
    import concurrent.futures

    try:
        from app.mcp.mongodb.mcp_runner import call_mcp_tool

        async def _mcp_fetch():
            doc = await call_mcp_tool("find", {
                "collection": "creator_memory",
                "filter": {"user_id": user_id},
                "limit": 1,
                "projection": {"topic_history": 1},
            })
            if doc and isinstance(doc, list) and len(doc) > 0:
                return doc[0].get("topic_history", [])
            return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, _mcp_fetch())
            result = future.result(timeout=8.0)

        if result is not None:
            return result
    except Exception as e:
        log.debug(f"[content_gap_agent] MCP fetch skipped: {e}")

    try:
        from app.mcp.mongodb.tools import find_one
        doc = find_one("creator_memory", {"user_id": user_id})
        return (doc or {}).get("topic_history", [])
    except Exception:
        return []


def _fetch_competitor_topics(niche: str) -> list[str]:
    try:
        from app.mcp.elastic.tools import search_competitor_content
        competitors = search_competitor_content(niche=niche, limit=20)
        return [c.get("title", "") for c in competitors if c.get("title")]
    except Exception as e:
        log.debug(f"[content_gap_agent] Elastic competitor fetch skipped: {e}")
        return []


def _fetch_audience_questions(niche: str) -> list[str]:
    try:
        from app.mcp.elastic.client import get_elastic_client
        client = get_elastic_client()
        if client is None:
            return []
        resp = client.search(
            index="audience_questions",
            body={
                "query": {"match": {"niche": niche}},
                "sort": [{"frequency": "desc"}],
                "size": 20,
            },
        )
        return [hit["_source"].get("question", "") for hit in resp["hits"]["hits"]]
    except Exception as e:
        log.debug(f"[content_gap_agent] Elastic audience questions fetch skipped: {e}")
        return []


def _fetch_trending_topics(niche: str) -> list[str]:
    try:
        from app.mcp.elastic.tools import search_trending_topics
        trends = search_trending_topics(niche=niche, days=30, limit=15)
        return [t.get("topic", "") for t in trends if t.get("topic")]
    except Exception as e:
        log.debug(f"[content_gap_agent] Elastic trending fetch skipped: {e}")
        return []


def _save_gaps_to_mongodb(user_id: int, gaps: list[str]) -> None:
    if not gaps or not user_id:
        return
    try:
        from app.mcp.mongodb.tools import upsert_one
        from datetime import datetime, timezone
        upsert_one(
            "creator_memory",
            {"user_id": user_id},
            {
                "$set": {
                    "content_gaps": gaps[:10],
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        log.info(f"[content_gap_agent] saved {len(gaps)} gaps to MongoDB")
    except Exception as e:
        log.warning(f"[content_gap_agent] failed to save gaps: {e}")


def _build_gap_prompt(
    niche: str,
    topic_history: list[str],
    competitor_titles: list[str],
    audience_questions: list[str],
    trending_topics: list[str],
) -> str:
    already_covered = "\n".join(f"  - {t}" for t in topic_history[-15:]) or "  (none yet)"
    competitors      = "\n".join(f"  - {t}" for t in competitor_titles[:15]) or "  (no data)"
    questions        = "\n".join(f"  - {q}" for q in audience_questions[:15]) or "  (no data)"
    trending         = "\n".join(f"  - {t}" for t in trending_topics[:10]) or "  (no data)"

    return f"""
You are a YouTube content strategist specializing in content gap analysis.

CREATOR NICHE: {niche}

TOPICS THIS CREATOR ALREADY COVERED:
{already_covered}

TOP COMPETITOR VIDEO TITLES IN THIS NICHE:
{competitors}

QUESTIONS AUDIENCES ACTUALLY ASK ABOUT THIS NICHE:
{questions}

CURRENTLY TRENDING TOPICS IN THIS NICHE:
{trending}

TASK:
Identify the 5 best content opportunities for this creator. A great opportunity is:
- Something the audience asks about (from the questions list)
- NOT already covered by this creator
- Either underserved by competitors OR approaching from a unique angle
- Relevant to current trends where possible

Return ONLY a valid JSON array of 5 opportunity objects:
[
  {{
    "topic": "specific video topic title",
    "opportunity_reason": "1-2 sentences: why this gap exists and why it's valuable",
    "suggested_angle": "the unique angle that differentiates from competitors",
    "urgency": "high | medium | low",
    "estimated_audience_demand": "high | medium | low"
  }},
  ...
]

No markdown. No preamble. JSON array only.
""".strip()


def content_gap_agent(
    user_id: int,
    niche: str,
    plan: str = "normal",
    topic_history: Optional[list[str]] = None,
) -> list[dict]:
    """
    Identify content gaps and opportunities for a creator.
    Always returns a list — never raises.
    """
    print(f"[content_gap_agent] analysing gaps for niche='{niche}' user={user_id}")

    history            = topic_history if topic_history is not None else _fetch_topic_history(user_id)
    competitor_titles  = _fetch_competitor_topics(niche)
    audience_questions = _fetch_audience_questions(niche)
    trending           = _fetch_trending_topics(niche)

    print(
        f"[content_gap_agent] data: "
        f"history={len(history)} | competitors={len(competitor_titles)} | "
        f"questions={len(audience_questions)} | trending={len(trending)}"
    )

    prompt = _build_gap_prompt(
        niche=niche,
        topic_history=history,
        competitor_titles=competitor_titles,
        audience_questions=audience_questions,
        trending_topics=trending,
    )

    try:
        model = get_model(plan, "research")
        raw   = generate_response(prompt, model)
        cleaned = re.sub(r"```[a-z]*", "", raw).strip().strip("`").strip()
        gaps    = json.loads(cleaned)

        if isinstance(gaps, list):
            gap_topics = [g.get("topic", "") for g in gaps if g.get("topic")]
            _save_gaps_to_mongodb(user_id, gap_topics)
            print(f"[content_gap_agent] found {len(gaps)} opportunities")
            return gaps[:5]
        return []

    except Exception as e:
        log.warning(f"[content_gap_agent] parse error: {e}")
        return []
