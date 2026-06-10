"""
youtube_agent.py

Thin orchestrator for the YouTube upload flow.
Delegates actual uploading to the youtube_provider layer
(YouTubeAPIProvider or YouTubeMCPProvider).

Used by the upload workflow graph — not called directly by routes.
"""
from sqlalchemy.orm import Session


class YouTubeAgent:
    """
    Orchestrates YouTube uploads within the upload workflow.
    Wraps the provider abstraction so the graph doesn't need to
    know which provider (API vs MCP) is active.
    """

    def upload(
        self,
        user_id: int,
        video_file_path: str,
        title: str,
        description: str,
        tags: list[str],
        category_id: str,
        privacy_status: str,
        db: Session,
    ) -> dict:
        """
        Upload a video to YouTube via the active provider.

        Returns:
            {
                "youtube_video_id":  str,
                "youtube_video_url": str,
                "upload_status":     "uploaded" | "failed",
                "error":             str | None,
            }
        """
        from app.youtube_provider import get_youtube_provider
        provider = get_youtube_provider(user_id=user_id, db=db)
        return provider.upload_video(
            video_file_path=video_file_path,
            title=title,
            description=description,
            tags=tags,
            category_id=category_id,
            privacy_status=privacy_status,
        )

    def upload_thumbnail(
        self,
        user_id: int,
        video_id: str,
        thumbnail_path: str,
        db: Session,
    ) -> dict:
        """
        Upload a custom thumbnail for an already-uploaded video.

        Returns:
            {
                "thumbnail_status": "uploaded" | "failed" | "skipped",
                "error":            str | None,
            }
        """
        from app.youtube_provider import get_youtube_provider
        provider = get_youtube_provider(user_id=user_id, db=db)
        return provider.upload_thumbnail(
            video_id=video_id,
            thumbnail_path=thumbnail_path,
        )
