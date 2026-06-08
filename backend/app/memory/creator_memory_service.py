"""
app/memory/creator_memory_service.py

CRUD operations for the creator_memory MongoDB collection.

Every method degrades gracefully when MongoDB is unavailable (client=None).
The workflow always continues — memory is additive, never blocking.

Key responsibilities:
  - get_or_create(): load memory at workflow start
  - sync_from_profile(): keep memory in sync with PostgreSQL profile
  - add_topic_to_history(): prevent duplicate research topics
  - add_successful_hook(): accumulate hooks the creator used
  - update_viral_patterns(): accumulate viral pattern knowledge
  - get_context_for_agents(): build the enriched context dict all agents use
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from app.memory.schemas import (
    CreatorMemoryDocument,
    CreatorMemoryProfile,
    AudienceIntelligence,
)

log = logging.getLogger(__name__)
COLLECTION = "creator_memory"
MAX_TOPIC_HISTORY = 50       # keep last 50 topics
MAX_HOOKS = 20               # keep last 20 successful hooks
MAX_PATTERNS = 30            # keep last 30 viral patterns


class CreatorMemoryService:

    def __init__(self, mongo_client):
        self._client = mongo_client
        self._db = None
        if mongo_client is not None:
            try:
                db_name = __import__("os").getenv(
                    "MONGODB_DB_NAME", "ai_content_studio"
                )
                self._db = mongo_client[db_name]
            except Exception as e:
                log.warning(f"[CreatorMemoryService] DB init failed: {e}")

    @property
    def _col(self):
        if self._db is None:
            return None
        return self._db[COLLECTION]

    # ── Core read/write ───────────────────────────────────────────

    def get_or_create(
        self,
        user_id: int,
        channel_id: str = "",
        channel_name: str = "",
    ) -> CreatorMemoryDocument:
        """
        Load the creator memory document for this user.
        Creates a blank document if one doesn't exist yet.
        Returns a blank document if MongoDB is unavailable.
        """
        if self._col is None:
            log.debug(f"[memory] MongoDB unavailable — returning blank memory for user {user_id}")
            return CreatorMemoryDocument(
                user_id=user_id,
                channel_id=channel_id,
                channel_name=channel_name,
            )

        try:
            doc = self._col.find_one({"user_id": user_id})
            if doc:
                return CreatorMemoryDocument.from_mongo(doc)

            # First time this user has run the workflow — create blank document
            new_doc = CreatorMemoryDocument(
                user_id=user_id,
                channel_id=channel_id,
                channel_name=channel_name,
            )
            self._col.insert_one(new_doc.to_mongo())
            log.info(f"[memory] Created new creator memory for user {user_id}")
            return new_doc

        except Exception as e:
            log.warning(f"[memory] get_or_create failed for user {user_id}: {e}")
            return CreatorMemoryDocument(user_id=user_id)

    def sync_from_profile(
        self,
        user_id: int,
        profile_data: dict,
        channel_id: str = "",
        channel_name: str = "",
    ) -> None:
        """
        Sync the memory document with the latest PostgreSQL creator profile.

        This is called every time `load_profile_node` runs so the memory
        document stays in sync with the authoritative PostgreSQL data.

        Critically: this PRESERVES accumulated fields (topic_history,
        successful_hooks, viral_patterns, audience_intelligence) while
        updating the core profile fields.

        Also fixes the bug: content_strengths and viral_patterns from the
        LLM output are NOW written to MongoDB so they're available to agents.
        """
        if self._col is None:
            return

        try:
            # Build the profile subdocument from PostgreSQL data
            audience = profile_data.get("audience", {})
            title_style = profile_data.get("title_style", {})
            desc_style = profile_data.get("description_style", {})

            profile_update = {
                "niche": profile_data.get("creator_niche", ""),
                "main_topics": profile_data.get("main_topics", profile_data.get("topics", [])),
                "audience_type": (
                    audience.get("audience_type", "")
                    if isinstance(audience, dict) else ""
                ),
                "audience_level": (
                    audience.get("audience_level", "beginner")
                    if isinstance(audience, dict) else "beginner"
                ),
                "title_style": (
                    title_style.get("style", "")
                    if isinstance(title_style, dict) else str(title_style)
                ),
                "description_style": (
                    desc_style.get("style", "")
                    if isinstance(desc_style, dict) else str(desc_style)
                ),
            }

            # These fields come from the LLM output (CreatorProfileOutput)
            # and were previously hardcoded to [] in load_profile_node.
            # Now they are stored in MongoDB and retrieved properly.
            content_strengths = profile_data.get("content_strengths", [])
            viral_patterns    = profile_data.get("viral_patterns", [])
            recommended_types = profile_data.get("recommended_video_types", [])

            update_ops: dict = {
                "$set": {
                    "profile": profile_update,
                    "channel_id": channel_id,
                    "channel_name": channel_name,
                    "updated_at": datetime.now(timezone.utc),
                }
            }

            # Only update content_strengths/viral_patterns if the profile
            # actually has non-empty values — don't overwrite accumulated
            # data with empty lists from a stale profile
            if content_strengths:
                update_ops["$set"]["content_strengths"] = content_strengths
            if viral_patterns:
                update_ops["$set"]["viral_patterns"] = viral_patterns
            if recommended_types:
                update_ops["$set"]["recommended_video_types"] = recommended_types

            self._col.update_one(
                {"user_id": user_id},
                update_ops,
                upsert=True,
            )
            log.debug(f"[memory] Synced profile for user {user_id}")

        except Exception as e:
            log.warning(f"[memory] sync_from_profile failed for user {user_id}: {e}")

    # ── Topic history ─────────────────────────────────────────────

    def add_topic_to_history(self, user_id: int, topic: str) -> None:
        """
        Append a topic to the creator's research history.
        Keeps only the last MAX_TOPIC_HISTORY topics (deque-like behaviour).
        """
        if self._col is None or not topic:
            return
        try:
            self._col.update_one(
                {"user_id": user_id},
                {
                    "$push": {
                        "topic_history": {
                            "$each":  [topic.strip()],
                            "$slice": -MAX_TOPIC_HISTORY,
                        }
                    },
                    "$set": {"updated_at": datetime.now(timezone.utc)},
                },
                upsert=True,
            )
        except Exception as e:
            log.warning(f"[memory] add_topic_to_history failed: {e}")

    def get_topic_history(self, user_id: int, limit: int = 10) -> list[str]:
        """Return the last `limit` researched topics for this creator."""
        if self._col is None:
            return []
        try:
            doc = self._col.find_one(
                {"user_id": user_id},
                {"topic_history": {"$slice": -limit}}
            )
            return (doc or {}).get("topic_history", [])
        except Exception as e:
            log.warning(f"[memory] get_topic_history failed: {e}")
            return []

    # ── Successful hooks ──────────────────────────────────────────

    def add_successful_hook(self, user_id: int, hook: str) -> None:
        """
        Add a hook line that the creator approved and used.
        ScriptAgent reads these and biases generation toward proven patterns.
        """
        if self._col is None or not hook:
            return
        try:
            self._col.update_one(
                {"user_id": user_id},
                {
                    "$addToSet": {"successful_hooks": hook.strip()},
                    "$set": {"updated_at": datetime.now(timezone.utc)},
                },
                upsert=True,
            )
        except Exception as e:
            log.warning(f"[memory] add_successful_hook failed: {e}")

    def get_successful_hooks(self, user_id: int) -> list[str]:
        """Return all accumulated successful hooks for this creator."""
        if self._col is None:
            return []
        try:
            doc = self._col.find_one({"user_id": user_id}, {"successful_hooks": 1})
            return (doc or {}).get("successful_hooks", [])
        except Exception as e:
            log.warning(f"[memory] get_successful_hooks failed: {e}")
            return []

    # ── Viral patterns ────────────────────────────────────────────

    def update_viral_patterns(self, user_id: int, patterns: list[str]) -> None:
        """
        Update viral patterns from the creator profile LLM output.
        Uses $addToSet so patterns accumulate without duplicates.
        """
        if self._col is None or not patterns:
            return
        try:
            self._col.update_one(
                {"user_id": user_id},
                {
                    "$addToSet": {
                        "viral_patterns": {"$each": [p.strip() for p in patterns if p]}
                    },
                    "$set": {"updated_at": datetime.now(timezone.utc)},
                },
                upsert=True,
            )
        except Exception as e:
            log.warning(f"[memory] update_viral_patterns failed: {e}")

    def get_viral_patterns(self, user_id: int) -> list[str]:
        """Return all accumulated viral patterns for this creator."""
        if self._col is None:
            return []
        try:
            doc = self._col.find_one({"user_id": user_id}, {"viral_patterns": 1})
            return (doc or {}).get("viral_patterns", [])
        except Exception as e:
            log.warning(f"[memory] get_viral_patterns failed: {e}")
            return []

    # ── Content strengths ─────────────────────────────────────────

    def get_content_strengths(self, user_id: int) -> list[str]:
        """Return content strengths for this creator."""
        if self._col is None:
            return []
        try:
            doc = self._col.find_one({"user_id": user_id}, {"content_strengths": 1})
            return (doc or {}).get("content_strengths", [])
        except Exception as e:
            log.warning(f"[memory] get_content_strengths failed: {e}")
            return []

    # ── Title patterns ────────────────────────────────────────────

    def add_successful_title_pattern(self, user_id: int, pattern: str) -> None:
        if self._col is None or not pattern:
            return
        try:
            self._col.update_one(
                {"user_id": user_id},
                {
                    "$addToSet": {"successful_title_patterns": pattern.strip()},
                    "$set": {"updated_at": datetime.now(timezone.utc)},
                },
                upsert=True,
            )
        except Exception as e:
            log.warning(f"[memory] add_successful_title_pattern failed: {e}")

    def get_successful_title_patterns(self, user_id: int) -> list[str]:
        if self._col is None:
            return []
        try:
            doc = self._col.find_one({"user_id": user_id}, {"successful_title_patterns": 1})
            return (doc or {}).get("successful_title_patterns", [])
        except Exception as e:
            log.warning(f"[memory] get_successful_title_patterns failed: {e}")
            return []

    # ── Performance counters ──────────────────────────────────────

    def increment_generation_count(self, user_id: int) -> None:
        if self._col is None:
            return
        try:
            self._col.update_one(
                {"user_id": user_id},
                {
                    "$inc": {"performance_summary.total_videos_generated": 1},
                    "$set": {"updated_at": datetime.now(timezone.utc)},
                },
                upsert=True,
            )
        except Exception as e:
            log.warning(f"[memory] increment_generation_count failed: {e}")

    def increment_upload_count(self, user_id: int) -> None:
        if self._col is None:
            return
        try:
            self._col.update_one(
                {"user_id": user_id},
                {
                    "$inc": {"performance_summary.total_videos_uploaded": 1},
                    "$set": {"updated_at": datetime.now(timezone.utc)},
                },
                upsert=True,
            )
        except Exception as e:
            log.warning(f"[memory] increment_upload_count failed: {e}")

    # ── Compound read for agent context ──────────────────────────

    def get_context_for_agents(self, user_id: int) -> dict:
        """
        Build the enriched memory context dict that all agents receive.

        This is the primary read path for the workflow.
        Returns a dict that is merged into creator_profile in state so
        existing agents receive enriched data without any signature changes.

        Returns an empty dict gracefully if MongoDB is unavailable.
        """
        if self._col is None:
            return {}

        try:
            doc = self._col.find_one({"user_id": user_id})
            if not doc:
                return {}

            return {
                # Fix: these were always [] before
                "content_strengths":       doc.get("content_strengths", []),
                "viral_patterns":          doc.get("viral_patterns", []),
                "recommended_video_types": doc.get("recommended_video_types", []),

                # Accumulated learning
                "successful_hooks":          doc.get("successful_hooks", []),
                "successful_title_patterns": doc.get("successful_title_patterns", []),
                "topic_history":             doc.get("topic_history", []),

                # Audience intelligence
                "audience_intelligence": doc.get("audience_intelligence", {}),
            }

        except Exception as e:
            log.warning(f"[memory] get_context_for_agents failed: {e}")
            return {}
