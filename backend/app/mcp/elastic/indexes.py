"""
app/mcp/elastic/indexes.py

Elasticsearch index mappings for the AI Content Studio intelligence layer.

Indexes:
  trending_topics     — what's trending in each niche (written by TrendAgent)
  competitor_content  — top-performing competitor videos (written by jobs/competitor_ingestion)
  content_index       — creator's own past content for dedup (written by save_generation_node)
  keyword_performance — which keywords drove views (written by upload_service after analytics)
  audience_questions  — what audiences ask about topics (future: YouTube comment analysis)

Call setup_indexes() once on startup. All mappings use explicit types
so Elasticsearch doesn't auto-map strings as keyword when we need full-text.
"""
import logging
from app.mcp.elastic.client import get_elastic_client

log = logging.getLogger(__name__)

# ── Index mappings ────────────────────────────────────────────────────────────

TRENDING_TOPICS_MAPPING = {
    "mappings": {
        "properties": {
            "niche":               {"type": "keyword"},
            "topic":               {"type": "text",    "fields": {"keyword": {"type": "keyword"}}},
            "score":               {"type": "float"},
            "search_volume_trend": {"type": "keyword"},  # rising | stable | declining
            "region":              {"type": "keyword"},
            "timeframe":           {"type": "keyword"},
            "related_keywords":    {"type": "keyword"},
            "source":              {"type": "keyword"},  # google_trends | youtube | manual
            "indexed_at":          {"type": "date"},
        }
    },
    "settings": {
        "number_of_shards":   1,
        "number_of_replicas": 0,
    },
}

COMPETITOR_CONTENT_MAPPING = {
    "mappings": {
        "properties": {
            "channel_id":       {"type": "keyword"},
            "channel_name":     {"type": "keyword"},
            "video_id":         {"type": "keyword"},
            "title":            {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "description":      {"type": "text"},
            "views":            {"type": "long"},
            "likes":            {"type": "long"},
            "comments":         {"type": "long"},
            "engagement_rate":  {"type": "float"},
            "published_at":     {"type": "date"},
            "topics":           {"type": "keyword"},
            "niche":            {"type": "keyword"},
            "audience_level":   {"type": "keyword"},
            "hook_pattern":     {"type": "keyword"},
            "thumbnail_style":  {"type": "keyword"},
            "indexed_at":       {"type": "date"},
        }
    },
    "settings": {
        "number_of_shards":   1,
        "number_of_replicas": 0,
    },
}

CONTENT_INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "user_id":        {"type": "integer"},
            "generation_id":  {"type": "integer"},
            "topic":          {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "selected_idea":  {"type": "text"},
            "script_hook":    {"type": "text"},
            "niche":          {"type": "keyword"},
            "created_at":     {"type": "date"},
        }
    },
    "settings": {
        "number_of_shards":   1,
        "number_of_replicas": 0,
    },
}

KEYWORD_PERFORMANCE_MAPPING = {
    "mappings": {
        "properties": {
            "user_id":             {"type": "integer"},
            "keyword":             {"type": "keyword"},
            "niche":               {"type": "keyword"},
            "used_in_video_id":    {"type": "keyword"},
            "title_position":      {"type": "integer"},
            "views_30_days":       {"type": "long"},
            "click_through_rate":  {"type": "float"},
            "avg_watch_percentage":{"type": "float"},
            "indexed_at":          {"type": "date"},
        }
    },
    "settings": {
        "number_of_shards":   1,
        "number_of_replicas": 0,
    },
}

AUDIENCE_QUESTIONS_MAPPING = {
    "mappings": {
        "properties": {
            "niche":       {"type": "keyword"},
            "topic":       {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "question":    {"type": "text"},
            "frequency":   {"type": "integer"},
            "source":      {"type": "keyword"},  # youtube_comments | reddit | manual
            "indexed_at":  {"type": "date"},
        }
    },
    "settings": {
        "number_of_shards":   1,
        "number_of_replicas": 0,
    },
}

ALL_INDEXES = {
    "trending_topics":    TRENDING_TOPICS_MAPPING,
    "competitor_content": COMPETITOR_CONTENT_MAPPING,
    "content_index":      CONTENT_INDEX_MAPPING,
    "keyword_performance":KEYWORD_PERFORMANCE_MAPPING,
    "audience_questions": AUDIENCE_QUESTIONS_MAPPING,
}


# ── Setup ─────────────────────────────────────────────────────────────────────

def setup_indexes() -> None:
    """
    Create all indexes if they don't exist.
    Called once from FastAPI lifespan startup when Elastic is configured.
    Safe to call on every restart — skips existing indexes.
    """
    client = get_elastic_client()
    if client is None:
        return

    for index_name, mapping in ALL_INDEXES.items():
        try:
            if not client.indices.exists(index=index_name):
                client.indices.create(index=index_name, body=mapping)
                log.info(f"[elastic] Created index: {index_name}")
                print(f"[elastic] Created index: {index_name}")
            else:
                log.debug(f"[elastic] Index already exists: {index_name}")
        except Exception as e:
            log.warning(f"[elastic] Index setup warning for '{index_name}': {e}")
