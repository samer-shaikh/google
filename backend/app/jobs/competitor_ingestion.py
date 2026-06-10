"""
app/jobs/competitor_ingestion.py

Background job: ingest competitor YouTube videos into Elasticsearch.
Uses YouTube Data API to search for top videos in a niche.

Can be triggered:
  a) POST /agent/competitors/refresh (via route)
  b) Directly in Python for testing/seeding

When YOUTUBE_API_KEY or ELASTICSEARCH_URL is not set, operations are no-ops.
"""
import os
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

log = logging.getLogger(__name__)


def _fetch_competitor_videos(niche: str, max_results: int = 20) -> list[dict]:
    """Fetch top videos in a niche using YouTube Data API."""
    try:
        from googleapiclient.discovery import build

        api_key = os.getenv("YOUTUBE_API_KEY", "").strip()
        if not api_key:
            log.debug("[competitor_ingestion] YOUTUBE_API_KEY not set — using seed data only")
            return []

        youtube = build("youtube", "v3", developerKey=api_key)

        # Search for top videos
        search_resp = youtube.search().list(
            part="snippet",
            q=niche,
            type="video",
            order="viewCount",
            maxResults=max_results,
        ).execute()

        video_ids = [item["id"]["videoId"] for item in search_resp.get("items", [])]
        if not video_ids:
            return []

        # Get statistics for each video
        stats_resp = youtube.videos().list(
            part="statistics,snippet",
            id=",".join(video_ids),
        ).execute()

        results = []
        for item in stats_resp.get("items", []):
            stats = item.get("statistics", {})
            snippet = item.get("snippet", {})
            views = int(stats.get("viewCount", 0))
            likes = int(stats.get("likeCount", 0))
            comments = int(stats.get("commentCount", 0))
            engagement = (likes + comments) / max(views, 1)

            results.append({
                "channel_id": snippet.get("channelId", ""),
                "channel_name": snippet.get("channelTitle", ""),
                "video_id": item["id"],
                "title": snippet.get("title", ""),
                "description": snippet.get("description", "")[:500],
                "views": views,
                "likes": likes,
                "comments": comments,
                "engagement_rate": round(engagement, 4),
                "published_at": snippet.get("publishedAt", ""),
                "topics": [niche.lower()],
                "niche": niche,
                "audience_level": "beginner",
                "hook_pattern": "unknown",
                "thumbnail_style": "unknown",
                "indexed_at": datetime.now(timezone.utc).isoformat(),
            })

        return results

    except Exception as e:
        log.debug(f"[competitor_ingestion] YouTube API fetch failed: {e}")
        return []


def run_competitor_ingestion(niche: str) -> dict:
    """
    Fetch competitor videos for a niche and index to Elasticsearch.

    Returns:
        {"indexed": int, "source": str, "elastic_enabled": bool}
    """
    from app.mcp.elastic.client import get_elastic_client
    client = get_elastic_client()
    if client is None:
        return {"indexed": 0, "source": "none", "elastic_enabled": False}

    print(f"[competitor_ingestion] fetching competitors for niche='{niche}'")

    # Try YouTube API first
    videos = _fetch_competitor_videos(niche)
    source = "youtube_api"

    # Fallback to seed data if API not available
    if not videos:
        from app.jobs.trend_ingestion import seed_competitor_data, seed_audience_questions
        indexed = seed_competitor_data(niche)
        indexed += seed_audience_questions(niche)
        return {"indexed": indexed, "source": "seed_data", "elastic_enabled": True}

    # Index YouTube API results
    indexed = 0
    for video in videos:
        try:
            client.index(
                index="competitor_content",
                id=video["video_id"],
                document=video,
            )
            indexed += 1
        except Exception as e:
            log.warning(f"[competitor_ingestion] Index error: {e}")

    print(f"[competitor_ingestion] indexed {indexed} competitor videos for '{niche}'")
    return {"indexed": indexed, "source": source, "elastic_enabled": True}


def run_competitor_ingestion_for_user(user_id: int) -> dict:
    """Convenience wrapper — looks up user's niche from MongoDB then ingests."""
    try:
        from app.mcp.mongodb.tools import find_one
        doc = find_one("creator_memory", {"user_id": user_id})
        niche = (doc or {}).get("profile", {}).get("niche", "")
        if not niche:
            return {"indexed": 0, "source": "none", "elastic_enabled": False}
        return run_competitor_ingestion(niche)
    except Exception as e:
        log.warning(f"[competitor_ingestion] for_user failed: {e}")
        return {"indexed": 0, "source": "error", "elastic_enabled": False}
