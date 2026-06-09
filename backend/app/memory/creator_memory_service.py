"""
app/memory/creator_memory_service.py

CRUD for the creator_memory MongoDB collection.
Uses app/mcp/mongodb/tools.py — degrades gracefully when MongoDB unavailable.
"""
import logging
from datetime import datetime, timezone

from app.mcp.mongodb.tools import (
    find_one, upsert_one, push_to_array, add_to_set,
    add_many_to_set, increment_field,
)
from app.mcp.mongodb.schemas import CreatorMemoryDocument

log = logging.getLogger(__name__)
COL = "creator_memory"
MAX_TOPICS = 50
MAX_HOOKS = 20


class CreatorMemoryService:

    def get_or_create(
        self,
        user_id: int,
        channel_id: str = "",
        channel_name: str = "",
    ) -> CreatorMemoryDocument:
        """Load memory document, creating blank one if missing."""
        doc = find_one(COL, {"user_id": user_id})
        if doc:
            return CreatorMemoryDocument.from_mongo(doc)

        # First run — create blank document
        blank = CreatorMemoryDocument(
            user_id=user_id,
            channel_id=channel_id,
            channel_name=channel_name,
        )
        upsert_one(
            COL,
            {"user_id": user_id},
            {"$setOnInsert": blank.to_mongo()},
        )
        log.info(f"[memory] Created new creator memory for user {user_id}")
        return blank

    def sync_from_profile(
        self,
        user_id: int,
        profile_data: dict,
        channel_id: str = "",
        channel_name: str = "",
    ) -> None:
        """
        Keep MongoDB memory in sync with PostgreSQL creator_profiles.
        Called every time load_memory_node runs.

        CRITICAL FIX: content_strengths and viral_patterns from the LLM output
        (CreatorProfileOutput) are NOW written here instead of being hardcoded [].
        This is the fix for the silent bug in load_profile_node.
        """
        audience = profile_data.get("audience", {})
        title_style = profile_data.get("title_style", {})
        desc_style = profile_data.get("description_style", {})

        profile_update = {
            "profile.niche": profile_data.get("creator_niche", ""),
            "profile.main_topics": profile_data.get(
                "main_topics", profile_data.get("topics", [])
            ),
            "profile.audience_type": (
                audience.get("audience_type", "")
                if isinstance(audience, dict) else ""
            ),
            "profile.audience_level": (
                audience.get("audience_level", "beginner")
                if isinstance(audience, dict) else "beginner"
            ),
            "profile.title_style": (
                title_style.get("style", "")
                if isinstance(title_style, dict) else str(title_style)
            ),
            "profile.description_style": (
                desc_style.get("style", "")
                if isinstance(desc_style, dict) else str(desc_style)
            ),
            "channel_id": channel_id,
            "channel_name": channel_name,
            "updated_at": datetime.now(timezone.utc),
        }

        # Only overwrite content_strengths / viral_patterns if the profile
        # has real values — preserve accumulated data from previous runs
        content_strengths = profile_data.get("content_strengths", [])
        viral_patterns = profile_data.get("viral_patterns", [])
        recommended_types = profile_data.get("recommended_video_types", [])

        if content_strengths:
            profile_update["content_strengths"] = content_strengths
        if viral_patterns:
            profile_update["viral_patterns"] = viral_patterns
        if recommended_types:
            profile_update["recommended_video_types"] = recommended_types

        upsert_one(
            COL,
            {"user_id": user_id},
            {"$set": profile_update},
        )

    def get_context_for_agents(self, user_id: int) -> dict:
        """
        Primary read path for the workflow.
        Returns enriched context dict merged into creator_profile in state.
        Returns {} gracefully if MongoDB unavailable.
        """
        doc = find_one(COL, {"user_id": user_id})
        if not doc:
            return {}

        return {
            # THE FIX: these are now real values from MongoDB, not hardcoded []
            "content_strengths":       doc.get("content_strengths", []),
            "viral_patterns":          doc.get("viral_patterns", []),
            "recommended_video_types": doc.get("recommended_video_types", []),
            # Accumulated learning
            "successful_hooks":          doc.get("successful_hooks", []),
            "successful_title_patterns": doc.get("successful_title_patterns", []),
            "topic_history":             doc.get("topic_history", []),
            # Audience intelligence
            "audience_intelligence":     doc.get("audience_intelligence", {}),
        }

    # ── Topic history ────────────────────────────────────────────

    def add_topic(self, user_id: int, topic: str) -> None:
        if not topic:
            return
        push_to_array(
            COL, {"user_id": user_id},
            "topic_history", topic.strip(),
            slice_limit=MAX_TOPICS,
        )

    def get_topic_history(self, user_id: int, limit: int = 10) -> list[str]:
        doc = find_one(COL, {"user_id": user_id})
        if not doc:
            return []
        history = doc.get("topic_history", [])
        return history[-limit:] if len(history) > limit else history

    # ── Hooks ────────────────────────────────────────────────────

    def add_hook(self, user_id: int, hook: str) -> None:
        if not hook:
            return
        add_to_set(COL, {"user_id": user_id}, "successful_hooks", hook.strip())

    def get_hooks(self, user_id: int) -> list[str]:
        doc = find_one(COL, {"user_id": user_id})
        return (doc or {}).get("successful_hooks", [])

    # ── Viral patterns ───────────────────────────────────────────

    def update_viral_patterns(self, user_id: int, patterns: list[str]) -> None:
        if not patterns:
            return
        add_many_to_set(
            COL, {"user_id": user_id},
            "viral_patterns",
            [p.strip() for p in patterns if p],
        )

    def get_viral_patterns(self, user_id: int) -> list[str]:
        doc = find_one(COL, {"user_id": user_id})
        return (doc or {}).get("viral_patterns", [])

    # ── Title patterns ───────────────────────────────────────────

    def add_title_pattern(self, user_id: int, pattern: str) -> None:
        if not pattern:
            return
        add_to_set(
            COL, {"user_id": user_id},
            "successful_title_patterns", pattern.strip(),
        )

    # ── Counters ─────────────────────────────────────────────────

    def increment_generations(self, user_id: int) -> None:
        increment_field(
            COL, {"user_id": user_id},
            "performance_summary.total_videos_generated",
        )

    def increment_uploads(self, user_id: int) -> None:
        increment_field(
            COL, {"user_id": user_id},
            "performance_summary.total_videos_uploaded",
        )
