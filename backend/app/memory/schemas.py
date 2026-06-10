"""
app/memory/schemas.py

Re-exports from app/mcp/mongodb/schemas.py for backward compatibility.
The canonical schema definitions live in app/mcp/mongodb/schemas.py.
"""
from app.mcp.mongodb.schemas import (
    AudienceIntelligence,
    PerformanceSummary,
    CreatorMemoryProfile,
    CreatorMemoryDocument,
    ResearchSessionDocument,
    ContentPieceSEO,
    ContentPieceDocument,
)

__all__ = [
    "AudienceIntelligence",
    "PerformanceSummary",
    "CreatorMemoryProfile",
    "CreatorMemoryDocument",
    "ResearchSessionDocument",
    "ContentPieceSEO",
    "ContentPieceDocument",
]
