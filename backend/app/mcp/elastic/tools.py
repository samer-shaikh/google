"""
app/mcp/elastic/tools.py

Elasticsearch tool functions — Phase 2.

All functions return empty values gracefully when Elastic is not configured.
When ELASTICSEARCH_URL is set, these activate automatically.
"""
import logging
from typing import Optional

from app.mcp.elastic.client import get_elastic_client

log = logging.getLogger(__name__)


def search_trending_topics(
    niche: str,
    days: int = 30,
    limit: int = 10,
) -> list[dict]:
    """
    Search for trending topics in the given niche.
    Used by ResearchAgent to enrich research with current trends.
    Returns [] if Elastic is not configured.
    """
    client = get_elastic_client()
    if client is None:
        return []
    try:
        resp = client.search(
            index="trending_topics",
            body={
                "query": {
                    "bool": {
                        "must": [
                            {"match": {"niche": niche}},
                        ],
                        "filter": [
                            {"range": {"indexed_at": {"gte": f"now-{days}d/d"}}}
                        ],
                    }
                },
                "sort": [{"score": "desc"}],
                "size": limit,
            },
        )
        return [hit["_source"] for hit in resp["hits"]["hits"]]
    except Exception as e:
        log.warning(f"[elastic.search_trending_topics] {e}")
        return []


def search_competitor_content(
    niche: str,
    audience_level: str = "",
    min_views: int = 10000,
    limit: int = 10,
) -> list[dict]:
    """
    Search for top-performing competitor content in the niche.
    Used by IdeaAgent to avoid saturated angles and find gaps.
    """
    client = get_elastic_client()
    if client is None:
        return []
    try:
        must = [{"match": {"topics": niche}}]
        if audience_level:
            must.append({"match": {"audience_level": audience_level}})

        resp = client.search(
            index="competitor_content",
            body={
                "query": {
                    "bool": {
                        "must": must,
                        "filter": [{"range": {"views": {"gte": min_views}}}],
                    }
                },
                "sort": [{"engagement_rate": "desc"}],
                "size": limit,
            },
        )
        return [hit["_source"] for hit in resp["hits"]["hits"]]
    except Exception as e:
        log.warning(f"[elastic.search_competitor_content] {e}")
        return []


def search_performing_keywords(
    user_id: int,
    niche: str,
    min_ctr: float = 0.03,
    limit: int = 15,
) -> list[dict]:
    """
    Search for keywords that drove views for this specific creator.
    Used by SEO agents in the upload workflow.
    """
    client = get_elastic_client()
    if client is None:
        return []
    try:
        resp = client.search(
            index="keyword_performance",
            body={
                "query": {
                    "bool": {
                        "must": [{"term": {"user_id": user_id}}],
                        "filter": [
                            {"range": {"click_through_rate": {"gte": min_ctr}}}
                        ],
                    }
                },
                "sort": [{"views_30_days": "desc"}],
                "size": limit,
            },
        )
        return [hit["_source"] for hit in resp["hits"]["hits"]]
    except Exception as e:
        log.warning(f"[elastic.search_performing_keywords] {e}")
        return []


def index_content_piece(document: dict) -> bool:
    """
    Index a completed content piece for future similarity search.
    Called by save_generation_node.
    """
    client = get_elastic_client()
    if client is None:
        return False
    try:
        doc_id = f"user{document.get('user_id')}_gen{document.get('generation_id')}"
        client.index(index="content_index", id=doc_id, document=document)
        return True
    except Exception as e:
        log.warning(f"[elastic.index_content_piece] {e}")
        return False
