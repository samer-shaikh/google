"""
app/memory/content_memory_service.py

Save and query completed content pieces in MongoDB.
"""
import logging
from app.mcp.mongodb.tools import upsert_one, find_many
from app.mcp.mongodb.schemas import ContentPieceDocument

log = logging.getLogger(__name__)
COL = "content_pieces"


class ContentMemoryService:

    def save_content_piece(
        self,
        user_id: int,
        generation_id: int,
        topic: str,
        selected_idea: str,
        script: str,
        thumbnail: str,
    ) -> None:
        """
        Save a completed content piece after save_generation_node completes.
        Extracts the hook from the script for future ScriptAgent context.
        """
        hook = self._extract_hook(script)
        word_count = len(script.split()) if script else 0

        doc = ContentPieceDocument(
            user_id=user_id,
            generation_id=generation_id,
            topic=topic,
            selected_idea=selected_idea,
            script_word_count=word_count,
            script_hook=hook,
            thumbnail_concept=thumbnail[:500] if thumbnail else "",
        )

        upsert_one(
            COL,
            {"generation_id": generation_id},
            {"$set": doc.to_mongo()},
        )
        log.debug(f"[content_memory] saved content piece gen_id={generation_id}")

    def get_recent_pieces(self, user_id: int, limit: int = 10) -> list[dict]:
        """Return recent content pieces for idea dedup and pattern analysis."""
        return find_many(
            COL,
            {"user_id": user_id},
            sort=[("created_at", -1)],
            limit=limit,
        )

    def get_past_hooks(self, user_id: int, limit: int = 5) -> list[str]:
        """Return recent hook lines for ScriptAgent context."""
        pieces = self.get_recent_pieces(user_id, limit=limit)
        return [p["script_hook"] for p in pieces if p.get("script_hook")]

    def get_past_topics(self, user_id: int, limit: int = 20) -> list[str]:
        """Return past topics for IdeaAgent duplicate detection."""
        pieces = self.get_recent_pieces(user_id, limit=limit)
        return [p["topic"] for p in pieces if p.get("topic")]

    def _extract_hook(self, script: str) -> str:
        """Extract the Hook section from the script."""
        if not script:
            return ""
        lines = script.splitlines()
        in_hook = False
        hook_lines = []
        for line in lines:
            if "# Hook" in line or "# HOOK" in line:
                in_hook = True
                continue
            if in_hook and line.startswith("#"):
                break
            if in_hook and line.strip():
                hook_lines.append(line.strip())
        return " ".join(hook_lines)[:300]
