"""
app/mcp/elastic/client.py

Elasticsearch MCP client — Phase 2.

Add to .env to activate:
    ELASTIC_MCP_URL=https://your-elastic-mcp-server/sse
    ELASTICSEARCH_URL=https://your-cluster.es.io:9243
    ELASTICSEARCH_API_KEY=your_api_key

Phase 1: Client returns None — all Elastic tools return empty/None gracefully.
Phase 2: Direct elasticsearch-py connection.
Phase 3: MCP tool-calling via Anthropic SDK.
"""
import os
import sys
import logging

log = logging.getLogger(__name__)
_MODULE = sys.modules[__name__]


def is_elastic_enabled() -> bool:
    return bool(
        os.getenv("ELASTICSEARCH_URL", "").strip() or
        os.getenv("ELASTIC_MCP_URL", "").strip()
    )


def get_elastic_client():
    """Return Elasticsearch client. None if not configured."""  

    if hasattr(_MODULE, "_client"):
        return _MODULE._client

    es_url = os.getenv("ELASTICSEARCH_URL", "").strip()
    api_key = os.getenv("ELASTICSEARCH_API_KEY", "").strip()

    if not es_url:
        log.info(
            "[elastic] ELASTICSEARCH_URL not set — "
            "trend intelligence disabled (Phase 2 feature). "
            "Add ELASTICSEARCH_URL to .env to enable."
        )
        _MODULE._client = None
        return None

    try:
        from elasticsearch import Elasticsearch

        if api_key:
            client = Elasticsearch(es_url, api_key=api_key)
        else:
            client = Elasticsearch(es_url)

        # Verify connection
        info = client.info()
        log.info(f"[elastic] Connected — cluster: {info['cluster_name']}")
        _MODULE._client = client
        return client

    except ImportError:
        log.info(
            "[elastic] elasticsearch-py not installed. "
            "Run: pip install elasticsearch\n"
            "Trend intelligence disabled."
        )
        _MODULE._client = None
        return None

    except Exception as e:
        log.warning(f"[elastic] Connection failed: {e}")
        _MODULE._client = None
        return None