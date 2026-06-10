"""
app/agents/trend_agent.py

Background trend intelligence agent.
Fetches trending topics for a given niche and writes them to Elasticsearch
so ResearchAgent can read them on the next workflow run.

Can be triggered:
  a) Via APScheduler / background job (daily/weekly)
  b) Via POST /agent/trends/refresh endpoint
  c) Directly in Python for testing

When Elastic is not configured, all operations are no-ops — safe to call always.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)


def _index_trend(client, topic: str, niche: str, source: str, score: float = 0.7) -> bool:
    """Index a single trending topic into Elasticsearch."""
    try:
        doc = {
            "niche": niche,
            "topic": topic,
            "score": score,
            "search_volume_trend": "rising",
            "region": "global",
            "timeframe": "last_7_days",
            "related_keywords": [],
            "source": source,
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
        doc_id = f"{niche.replace(' ', '_')}_{topic[:40].replace(' ', '_')}"
        client.index(index="trending_topics", id=doc_id, document=doc)
        return True
    except Exception as e:
        log.warning(f"[trend_agent] Failed to index topic '{topic}': {e}")
        return False


def _fetch_youtube_trends(niche: str) -> list[dict]:
    """
    Fetch trending YouTube searches for a niche.
    Uses YouTube Data API search endpoint (videos, order=viewCount, last 7 days).
    Returns list of {topic, score} dicts.
    """
    try:
        import os
        from googleapiclient.discovery import build

        api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
        if not api_key:
            log.debug("[trend_agent] YOUTUBE_API_KEY not set — skipping YouTube trends")
            return []

        youtube = build("youtube", "v3", developerKey=api_key)
        response = youtube.search().list(
            part="snippet",
            q=niche,
            type="video",
            order="viewCount",
            publishedAfter=_days_ago_iso(7),
            maxResults=15,
        ).execute()

        results = []
        for item in response.get("items", []):
            title = item.get("snippet", {}).get("title", "")
            if title:
                results.append({"topic": title, "score": 0.8, "source": "youtube"})
        return results

    except Exception as e:
        log.debug(f"[trend_agent] YouTube trends fetch failed: {e}")
        return []


def _fetch_manual_seeds(niche: str) -> list[dict]:
    """
    Manual seed topics for niches — used as fallback when APIs are unavailable.
    These give Elastic data to work with immediately without API keys.
    """
    seeds = {
        "python": [
            "Python for AI development 2025",
            "FastAPI vs Flask which is better",
            "Python async programming explained",
            "Pydantic v2 tutorial",
            "Python type hints complete guide",
        ],
        "machine learning": [
            "LLMs explained simply",
            "Fine-tuning vs RAG which to use",
            "Vector databases for beginners",
            "Prompt engineering best practices",
            "AI agents with LangGraph tutorial",
        ],
        "data science": [
            "Pandas vs Polars performance comparison",
            "Data science portfolio projects 2025",
            "SQL for data scientists",
            "Feature engineering techniques",
            "Data cleaning with Python",
        ],
    }

    niche_lower = niche.lower()
    for key, topics in seeds.items():
        if key in niche_lower:
            return [{"topic": t, "score": 0.6, "source": "manual_seed"} for t in topics]

    # Generic fallback
    return [
        {"topic": f"Beginner guide to {niche}", "score": 0.5, "source": "manual_seed"},
        {"topic": f"Advanced {niche} techniques", "score": 0.5, "source": "manual_seed"},
        {"topic": f"{niche} projects for beginners", "score": 0.5, "source": "manual_seed"},
    ]


def _days_ago_iso(days: int) -> str:
    from datetime import timedelta
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def run_trend_agent(niche: str, force_seeds: bool = False) -> dict:
    """
    Fetch trending topics for a niche and write them to Elasticsearch.

    Args:
        niche:        Creator niche string (e.g. "Python programming")
        force_seeds:  If True, always write seed data even if YouTube succeeds

    Returns:
        {"indexed": int, "sources": list[str], "elastic_enabled": bool}
    """
    from app.mcp.elastic.client import get_elastic_client
    client = get_elastic_client()

    if client is None:
        log.info("[trend_agent] Elasticsearch not configured — trend indexing skipped")
        return {"indexed": 0, "sources": [], "elastic_enabled": False}

    print(f"[trend_agent] fetching trends for niche='{niche}'")

    all_topics: list[dict] = []
    sources_used: list[str] = []

    # Try YouTube API first
    yt_topics = _fetch_youtube_trends(niche)
    if yt_topics:
        all_topics.extend(yt_topics)
        sources_used.append("youtube")

    # Always add manual seeds (either as fallback or supplement)
    if not yt_topics or force_seeds:
        seed_topics = _fetch_manual_seeds(niche)
        all_topics.extend(seed_topics)
        sources_used.append("manual_seed")

    # Index everything to Elastic
    indexed = 0
    for item in all_topics:
        if _index_trend(client, item["topic"], niche, item["source"], item.get("score", 0.6)):
            indexed += 1

    print(f"[trend_agent] indexed {indexed} trending topics for '{niche}' via {sources_used}")
    log.info(f"[trend_agent] indexed {indexed} topics | sources={sources_used}")

    return {"indexed": indexed, "sources": sources_used, "elastic_enabled": True}


def run_trend_agent_for_user(user_id: int) -> dict:
    """
    Convenience wrapper — looks up user's niche from MongoDB creator_memory
    then calls run_trend_agent.
    """
    try:
        from app.mcp.mongodb.tools import find_one
        doc = find_one("creator_memory", {"user_id": user_id})
        niche = (doc or {}).get("profile", {}).get("niche", "")
        if not niche:
            log.warning(f"[trend_agent] No niche found for user {user_id}")
            return {"indexed": 0, "sources": [], "elastic_enabled": False}
        return run_trend_agent(niche)
    except Exception as e:
        log.warning(f"[trend_agent] run_trend_agent_for_user failed: {e}")
        return {"indexed": 0, "sources": [], "elastic_enabled": False}
