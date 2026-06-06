from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build
from datetime import datetime, timezone
import os

from app.models.youtube_account import YouTubeAccount
from app.models.youtube_video import YouTubeVideo


class YouTubeResearchAgent:

    def _get_credentials(self, account: YouTubeAccount, db: Session) -> Credentials:
        """
        Build Credentials and refresh the access token if it has expired.
        Previously the token was used as-is, causing silent 401 failures
        after the 1-hour expiry window.
        """
        credentials = Credentials(
            token=account.access_token,
            refresh_token=account.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
            expiry=account.token_expiry,
        )

        # Refresh if expired or about to expire
        if credentials.expired and credentials.refresh_token:
            credentials.refresh(GoogleRequest())
            # Persist the new access token so the next call doesn't need to refresh again
            account.access_token = credentials.token
            account.token_expiry = credentials.expiry
            db.commit()

        return credentials

    def _fetch_video_details(self, youtube, video_ids: list[str]) -> list[dict]:
        """
        Batch-fetch statistics + snippet for a list of video IDs.
        playlistItems only returns snippet — we need a second call for stats.
        """
        if not video_ids:
            return []

        response = youtube.videos().list(
            part="snippet,statistics,contentDetails",
            id=",".join(video_ids),
            maxResults=50,
        ).execute()

        return response.get("items", [])

    def run(self, user_id: int, db: Session) -> dict:
        account = (
            db.query(YouTubeAccount)
            .filter(YouTubeAccount.user_id == user_id)
            .first()
        )

        if not account:
            raise Exception("YouTube account not connected")

        credentials = self._get_credentials(account, db)
        youtube = build("youtube", "v3", credentials=credentials)

        # Step 1: Get the uploads playlist ID for this channel
        channel_response = youtube.channels().list(
            part="contentDetails,snippet,statistics",
            mine=True,
        ).execute()

        if not channel_response.get("items"):
            raise Exception("No YouTube channel found")

        channel = channel_response["items"][0]
        uploads_playlist_id = (
            channel["contentDetails"]["relatedPlaylists"]["uploads"]
        )

        # Step 2: Get the list of recent video IDs from the uploads playlist
        playlist_response = youtube.playlistItems().list(
            part="snippet",
            playlistId=uploads_playlist_id,
            maxResults=50,
        ).execute()

        playlist_items = playlist_response.get("items", [])
        video_ids = [
            item["snippet"]["resourceId"]["videoId"]
            for item in playlist_items
            if item["snippet"].get("resourceId", {}).get("kind") == "youtube#video"
        ]

        if not video_ids:
            return {"success": True, "videos_found": 0, "videos_saved": 0}

        # Step 3: Fetch full video details (stats, description, etc.)
        video_items = self._fetch_video_details(youtube, video_ids)

        # Step 4: Upsert videos into youtube_videos table
        # ON CONFLICT DO NOTHING prevents duplicates on re-runs
        saved = 0
        for item in video_items:
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})

            published_raw = snippet.get("publishedAt")
            published_at = None
            if published_raw:
                published_at = datetime.fromisoformat(
                    published_raw.replace("Z", "+00:00")
                )

            stmt = (
                pg_insert(YouTubeVideo)
                .values(
                    user_id=user_id,
                    video_id=item["id"],
                    title=snippet.get("title"),
                    description=snippet.get("description"),
                    views=int(stats.get("viewCount", 0)),
                    likes=int(stats.get("likeCount", 0)),
                    comments=int(stats.get("commentCount", 0)),
                    published_at=published_at,
                    is_analyzed=False,
                )
                .on_conflict_do_update(
                    index_elements=["video_id"],
                    set_={
                        # Update stats on re-fetch so numbers stay current
                        "views": int(stats.get("viewCount", 0)),
                        "likes": int(stats.get("likeCount", 0)),
                        "comments": int(stats.get("commentCount", 0)),
                        "fetched_at": datetime.now(timezone.utc),
                    },
                )
            )
            db.execute(stmt)
            saved += 1

        db.commit()

        return {
            "success": True,
            "channel_name": channel["snippet"]["title"],
            "videos_found": len(video_ids),
            "videos_saved": saved,
        }
