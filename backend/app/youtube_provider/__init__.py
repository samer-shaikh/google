"""
youtube_provider/__init__.py — Provider factory

Priority:
  1. YouTubeMCPProvider   — if YOUTUBE_MCP_URL is set in .env
  2. YouTubeAPIProvider   — always available as fallback

The upload workflow calls get_youtube_provider() and gets back
a YouTubeProviderBase instance without caring which one it is.
"""
import os


def get_youtube_provider(user_id: int, db):
    """
    Return the correct YouTube provider for the current environment.

    Args:
        user_id: The authenticated user's ID (for loading OAuth tokens)
        db:      SQLAlchemy session (for YouTubeAPIProvider credential loading)

    Returns:
        YouTubeProviderBase instance
    """
    mcp_url = os.getenv("YOUTUBE_MCP_URL", "").strip()

    if mcp_url:
        try:
            from app.youtube_provider.youtube_mcp_provider import YouTubeMCPProvider
            print(f"[youtube_provider] using MCP provider: {mcp_url}")
            return YouTubeMCPProvider(mcp_url=mcp_url, user_id=user_id)
        except NotImplementedError:
            print("[youtube_provider] MCP provider not implemented — falling back to API")

    from app.youtube_provider.youtube_api_provider import YouTubeAPIProvider
    print("[youtube_provider] using YouTube Data API provider")
    return YouTubeAPIProvider(user_id=user_id, db=db)
