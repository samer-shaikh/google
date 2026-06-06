"""
base.py — Abstract YouTube provider interface

The upload workflow only calls methods on this interface.
It does not care whether the implementation is the Data API or MCP.
"""
from abc import ABC, abstractmethod


class YouTubeProviderBase(ABC):

    @abstractmethod
    def upload_video(
        self,
        video_file_path: str,
        title: str,
        description: str,
        tags: list[str],
        category_id: str,
        privacy_status: str,
    ) -> dict:
        """
        Upload a video file to YouTube.

        Returns:
            {
                "youtube_video_id": str,
                "youtube_video_url": str,
                "upload_status": "uploaded" | "failed",
                "error": str | None,
            }
        """

    @abstractmethod
    def upload_thumbnail(
        self,
        video_id: str,
        thumbnail_path: str,
    ) -> dict:
        """
        Upload a thumbnail image for an existing video.

        Returns:
            {
                "thumbnail_status": "uploaded" | "failed",
                "error": str | None,
            }
        """

    @abstractmethod
    def refresh_credentials(self) -> bool:
        """
        Refresh OAuth tokens if expired.
        Returns True if refresh succeeded or was not needed.
        """
