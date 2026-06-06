"""
youtube_mcp_provider.py — YouTube MCP provider stub

When a YouTube MCP server is configured and connected,
this provider delegates upload calls to it instead of the Data API.

Current status: STUB — raises NotImplementedError.
Implement when MCP server URL is available.

To activate: set YOUTUBE_MCP_URL in .env
"""
from app.youtube_provider.base import YouTubeProviderBase


class YouTubeMCPProvider(YouTubeProviderBase):
    """
    YouTube provider that uses an MCP server for uploads.
    Priority over YouTubeAPIProvider when YOUTUBE_MCP_URL is set.
    """

    def __init__(self, mcp_url: str, user_id: int):
        self.mcp_url = mcp_url
        self.user_id = user_id

    def upload_video(
        self,
        video_file_path: str,
        title: str,
        description: str,
        tags: list[str],
        category_id: str,
        privacy_status: str,
    ) -> dict:
        # TODO: implement MCP tool call
        # import requests
        # response = requests.post(f"{self.mcp_url}/tools/upload_video", json={...})
        raise NotImplementedError(
            "YouTubeMCPProvider.upload_video not yet implemented. "
            "Set YOUTUBE_MCP_URL and implement the MCP tool call."
        )

    def upload_thumbnail(self, video_id: str, thumbnail_path: str) -> dict:
        # TODO: implement MCP tool call
        raise NotImplementedError(
            "YouTubeMCPProvider.upload_thumbnail not yet implemented."
        )

    def refresh_credentials(self) -> bool:
        # MCP server manages credentials independently
        return True
