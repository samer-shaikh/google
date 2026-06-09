"""
app/mcp/mongodb/tools.py

MongoDB tool functions called by memory services.

In Phase 1, these are regular Python functions that call pymongo directly.
In Phase 2 (MCP URL activated), these will be replaced by MCP tool calls
through the Anthropic SDK — memory services need no changes.

All functions return None / empty values gracefully when MongoDB is unavailable.
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Any

from app.mcp.mongodb.client import get_mongodb_db

log = logging.getLogger(__name__)


# ── Generic tools ─────────────────────────────────────────────────────────────

def find_one(collection: str, query: dict) -> Optional[dict]:
    """Find a single document matching query."""
    db = get_mongodb_db()
    if db is None:
        return None
    try:
        doc = db[collection].find_one(query)
        if doc:
            doc.pop("_id", None)
        return doc
    except Exception as e:
        log.warning(f"[mongodb.find_one] {collection} {query}: {e}")
        return None


def find_many(
    collection: str,
    query: dict,
    sort: Optional[list] = None,
    limit: int = 20,
) -> list[dict]:
    """Find multiple documents."""
    db = get_mongodb_db()
    if db is None:
        return []
    try:
        cursor = db[collection].find(query)
        if sort:
            cursor = cursor.sort(sort)
        cursor = cursor.limit(limit)
        docs = []
        for doc in cursor:
            doc.pop("_id", None)
            docs.append(doc)
        return docs
    except Exception as e:
        log.warning(f"[mongodb.find_many] {collection}: {e}")
        return []


def upsert_one(collection: str, filter_query: dict, update: dict) -> bool:
    """Upsert a document. Returns True on success."""
    db = get_mongodb_db()
    if db is None:
        return False
    try:
        db[collection].update_one(filter_query, update, upsert=True)
        return True
    except Exception as e:
        log.warning(f"[mongodb.upsert_one] {collection}: {e}")
        return False


def insert_one(collection: str, document: dict) -> bool:
    """Insert a single document. Returns True on success."""
    db = get_mongodb_db()
    if db is None:
        return False
    try:
        db[collection].insert_one(document)
        return True
    except Exception as e:
        log.warning(f"[mongodb.insert_one] {collection}: {e}")
        return False


def push_to_array(
    collection: str,
    filter_query: dict,
    field: str,
    value: Any,
    slice_limit: Optional[int] = None,
) -> bool:
    """
    Append a value to an array field.
    If slice_limit set, keeps only the last N elements (deque behaviour).
    """
    db = get_mongodb_db()
    if db is None:
        return False
    try:
        if slice_limit:
            push_op = {"$each": [value], "$slice": -abs(slice_limit)}
        else:
            push_op = {"$each": [value]}

        db[collection].update_one(
            filter_query,
            {
                "$push": {field: push_op},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
            upsert=True,
        )
        return True
    except Exception as e:
        log.warning(f"[mongodb.push_to_array] {collection}.{field}: {e}")
        return False


def add_to_set(
    collection: str,
    filter_query: dict,
    field: str,
    value: Any,
) -> bool:
    """Add a value to an array only if not already present ($addToSet)."""
    db = get_mongodb_db()
    if db is None:
        return False
    try:
        db[collection].update_one(
            filter_query,
            {
                "$addToSet": {field: value},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
            upsert=True,
        )
        return True
    except Exception as e:
        log.warning(f"[mongodb.add_to_set] {collection}.{field}: {e}")
        return False


def add_many_to_set(
    collection: str,
    filter_query: dict,
    field: str,
    values: list,
) -> bool:
    """Add multiple values to a set field ($addToSet $each)."""
    db = get_mongodb_db()
    if db is None or not values:
        return False
    try:
        db[collection].update_one(
            filter_query,
            {
                "$addToSet": {field: {"$each": values}},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
            upsert=True,
        )
        return True
    except Exception as e:
        log.warning(f"[mongodb.add_many_to_set] {collection}.{field}: {e}")
        return False


def increment_field(
    collection: str,
    filter_query: dict,
    field: str,
    amount: int = 1,
) -> bool:
    """Increment a numeric field by amount."""
    db = get_mongodb_db()
    if db is None:
        return False
    try:
        db[collection].update_one(
            filter_query,
            {
                "$inc": {field: amount},
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
            upsert=True,
        )
        return True
    except Exception as e:
        log.warning(f"[mongodb.increment_field] {collection}.{field}: {e}")
        return False
