"""
app/memory/research_memory_service.py

Save and query research sessions in MongoDB.
"""
import logging
from app.mcp.mongodb.tools import insert_one, find_many
from app.mcp.mongodb.schemas import ResearchSessionDocument

log = logging.getLogger(__name__)
COL = "research_sessions"


class ResearchMemoryService:

    def save_session(
        self,
        user_id: int,
        generation_id: int,
        topic: str,
        research_output: str,
    ) -> None:
        """Save a research session document after research_node completes."""
        doc = ResearchSessionDocument(
            user_id=user_id,
            generation_id=generation_id,
            topic=topic,
            research_output=research_output,
            key_insights=self._extract_insights(research_output),
            hook_ideas=self._extract_hooks(research_output),
        )
        insert_one(COL, doc.to_mongo())
        log.debug(f"[research_memory] saved session for user {user_id} topic={topic[:30]}")

    def get_recent_sessions(self, user_id: int, limit: int = 5) -> list[dict]:
        """Return the most recent research sessions for topic history context."""
        return find_many(
            COL,
            {"user_id": user_id},
            sort=[("created_at", -1)],
            limit=limit,
        )

    def _extract_insights(self, research_output: str) -> list[str]:
        """
        Extract bullet-point insights from research output text.
        Simple heuristic — works with the structured research.txt prompt output.
        """
        insights = []
        for line in research_output.splitlines():
            line = line.strip()
            if line.startswith("- ") and len(line) > 10:
                insights.append(line[2:].strip())
        return insights[:10]

    def _extract_hooks(self, research_output: str) -> list[str]:
        """Extract hook ideas from the Hook Ideas section of research output."""
        hooks = []
        in_hooks_section = False
        for line in research_output.splitlines():
            stripped = line.strip()
            if "Hook Ideas" in stripped or "## 6" in stripped:
                in_hooks_section = True
                continue
            if in_hooks_section and stripped.startswith("##"):
                break
            if in_hooks_section and stripped.startswith(("- ", "• ", "* ")):
                hook = stripped.lstrip("-•* ").strip()
                if hook:
                    hooks.append(hook)
        return hooks[:10]
