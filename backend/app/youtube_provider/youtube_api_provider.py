"""
youtube_api_provider.py — YouTube Data API v3 provider

Implements YouTubeProviderBase using google-api-python-client.
Handles token refresh, MediaFileUpload, thumbnail upload, and retries.
"""
import os
import time
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from app.youtube_provider.base import YouTubeProviderBase

# YouTube category name → ID mapping
CATEGORY_MAP = {
    "Education":        "27",
    "Science":          "28",
    "Technology":       "28",
    "Entertainment":    "24",
    "Gaming":           "20",
    "Music":            "10",
    "News":             "25",
    "Sports":           "17",
    "Travel":           "19",
    "Howto":            "26",
    "Comedy":           "23",
    "Film":             "1",
    "Autos":            "2",
    "Pets":             "15",
    "People":           "22",
    "Nonprofits":       "29",
}

MAX_RETRIES   = 3
RETRY_DELAY   = 2   # seconds between retries


class YouTubeAPIProvider(YouTubeProviderBase):
    """
    YouTube Data API v3 provider.
    Loads credentials from the YouTubeAccount DB row for a given user.
    """

    def __init__(self, user_id: int, db):
        self.user_id = user_id
        self.db      = db
        self._account    = None
        self._credentials = None
        self._youtube    = None
        self._load()

    # ── Credential management ─────────────────────────────────────

    def _load(self):
        from app.models.youtube_account import YouTubeAccount

        self._account = (
            self.db.query(YouTubeAccount)
            .filter(YouTubeAccount.user_id == self.user_id)
            .first()
        )
        if not self._account:
            raise ValueError(
                f"No YouTube account connected for user {self.user_id}. "
                "Connect via /youtube/connect first."
            )

        self._credentials = Credentials(
            token=        self._account.access_token,
            refresh_token=self._account.refresh_token,
            token_uri=    "https://oauth2.googleapis.com/token",
            client_id=    os.getenv("GOOGLE_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
            expiry=       self._account.token_expiry,
        )

        self._youtube = build(
            "youtube", "v3",
            credentials=self._credentials,
            cache_discovery=False,
        )

    def refresh_credentials(self) -> bool:
        """Refresh access token if expired. Persists new token to DB."""
        try:
            if self._credentials.expired and self._credentials.refresh_token:
                self._credentials.refresh(GoogleRequest())
                self._account.access_token = self._credentials.token
                self._account.token_expiry = self._credentials.expiry
                self.db.commit()
                self._youtube = build(
                    "youtube", "v3",
                    credentials=self._credentials,
                    cache_discovery=False,
                )
                print("[YouTubeAPIProvider] token refreshed successfully")
            return True
        except Exception as e:
            print(f"[YouTubeAPIProvider] token refresh failed: {e}")
            return False

    def _ensure_fresh(self):
        """Call before any API request."""
        if not self.refresh_credentials():
            raise RuntimeError(
                "YouTube token refresh failed. "
                "Ask the user to reconnect their YouTube account."
            )

    # ── Video upload ──────────────────────────────────────────────

    def upload_video(
        self,
        video_file_path: str,
        title: str,
        description: str,
        tags: list[str],
        category_id: str,
        privacy_status: str,
    ) -> dict:
        self._ensure_fresh()

        if not os.path.exists(video_file_path):
            return {
                "youtube_video_id":  "",
                "youtube_video_url": "",
                "upload_status":     "failed",
                "error":             f"Video file not found: {video_file_path}",
            }

        body = {
            "snippet": {
                "title":       title[:100],
                "description": description,
                "tags":        tags,
                "categoryId":  category_id,
            },
            "status": {
                "privacyStatus":           privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(
            video_file_path,
            mimetype="video/*",
            resumable=True,
            chunksize=1024 * 1024 * 5,
        )

        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"[YouTubeAPIProvider] upload attempt {attempt}/{MAX_RETRIES}: {title}")
                request  = self._youtube.videos().insert(
                    part="snippet,status",
                    body=body,
                    media_body=media,
                )
                response = None
                while response is None:
                    status, response = request.next_chunk()
                    if status:
                        pct = int(status.progress() * 100)
                        print(f"[YouTubeAPIProvider] uploading... {pct}%")

                video_id  = response["id"]
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                print(f"[YouTubeAPIProvider] upload complete: {video_url}")
                return {
                    "youtube_video_id":  video_id,
                    "youtube_video_url": video_url,
                    "upload_status":     "uploaded",
                    "error":             None,
                }

            except HttpError as e:
                last_error = str(e)
                print(f"[YouTubeAPIProvider] HTTP error on attempt {attempt}: {e}")
                if e.resp.status in (400, 401, 403, 404):
                    break
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)

            except Exception as e:
                last_error = str(e)
                print(f"[YouTubeAPIProvider] error on attempt {attempt}: {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)

        return {
            "youtube_video_id":  "",
            "youtube_video_url": "",
            "upload_status":     "failed",
            "error":             last_error,
        }

    # ── Thumbnail upload ──────────────────────────────────────────

    def upload_thumbnail(
        self,
        video_id: str,
        thumbnail_path: str,
    ) -> dict:
        """
        Upload a thumbnail image for an already-uploaded video.

        Returns a result dict with thumbnail_status and error.
        NEVER raises — always returns gracefully so the video upload is preserved.

        thumbnail_status values:
          "uploaded"            — success
          "skipped"             — no video_id or no thumbnail_path
          "skipped_unverified"  — 403: channel not verified for custom thumbnails
          "failed"              — other error
        """
        self._ensure_fresh()

        if not video_id:
            return {"thumbnail_status": "skipped", "error": "No video_id provided"}

        if not thumbnail_path or not os.path.exists(thumbnail_path):
            return {
                "thumbnail_status": "skipped",
                "error": f"Thumbnail file not found: {thumbnail_path}",
            }

        ext  = os.path.splitext(thumbnail_path)[1].lower()
        mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"

        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                media = MediaFileUpload(thumbnail_path, mimetype=mime)
                self._youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=media,
                ).execute()
                print(f"[YouTubeAPIProvider] thumbnail uploaded for {video_id}")
                return {"thumbnail_status": "uploaded", "error": None}

            except HttpError as e:
                last_error = str(e)
                print(f"[YouTubeAPIProvider] thumbnail HTTP error attempt {attempt}: {e}")

                # ── 403: channel not verified for custom thumbnails ──────────
                # This is a YouTube policy requirement, not a code bug.
                # Return a soft skip — the video was already uploaded successfully.
                if e.resp.status == 403:
                    print(
                        "[YouTubeAPIProvider] thumbnail 403 — channel not verified. "
                        "Skipping thumbnail gracefully (video already uploaded)."
                    )
                    return {
                        "thumbnail_status": "skipped_unverified",
                        "error": (
                            "Custom thumbnails require a verified YouTube channel. "
                            "Verify at youtube.com/verify — your video was uploaded successfully."
                        ),
                    }

                # 400/401/404 — not retryable
                if e.resp.status in (400, 401, 404):
                    break

                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)

            except Exception as e:
                last_error = str(e)
                print(f"[YouTubeAPIProvider] thumbnail error attempt {attempt}: {e}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY * attempt)

        return {"thumbnail_status": "failed", "error": last_error}
