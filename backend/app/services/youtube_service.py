"""
youtube_service.py

Real YouTube Data API v3 helpers used by creator_profile_workflow.
Previously this file returned hardcoded mock data, which meant every
creator profile was built from fake videos.
"""
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from googleapiclient.discovery import build
from sqlalchemy.orm import Session
from datetime import datetime
import os

from app.models.youtube_account import YouTubeAccount
from app.database import SessionLocal


def _get_youtube_client(user_id: int, db: Session):
    """Build an authenticated YouTube API client for the given user."""
    account = (
        db.query(YouTubeAccount)
        .filter(YouTubeAccount.user_id == user_id)
        .first()
    )
    if not account:
        raise Exception(f"No YouTube account connected for user {user_id}")

    credentials = Credentials(
        token=account.access_token,
        refresh_token=account.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        expiry=account.token_expiry,
    )

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(GoogleRequest())
        account.access_token = credentials.token
        account.token_expiry = credentials.expiry
        db.commit()

    return build("youtube", "v3", credentials=credentials)


def get_channel_info(user_id: int, db: Session) -> dict:
    """Fetch channel metadata for the authenticated user."""
    youtube = _get_youtube_client(user_id, db)
    response = youtube.channels().list(
        part="snippet,statistics", mine=True
    ).execute()

    if not response.get("items"):
        raise Exception("No YouTube channel found")

    channel = response["items"][0]
    snippet = channel["snippet"]
    stats = channel["statistics"]

    return {
        "channel_id": channel["id"],
        "channel_name": snippet["title"],
        "description": snippet.get("description", ""),
        "subscribers": int(stats.get("subscriberCount", 0)),
        "total_views": int(stats.get("viewCount", 0)),
        "video_count": int(stats.get("videoCount", 0)),
        "country": snippet.get("country", ""),
        "published_at": snippet.get("publishedAt", ""),
    }


def get_recent_videos(user_id: int, db: Session, max_results: int = 30) -> list[dict]:
    """
    Fetch recent videos for the authenticated user's channel.
    Samples up to max_results videos — capped to avoid huge LLM context.
    """
    youtube = _get_youtube_client(user_id, db)

    # Get uploads playlist
    channel_response = youtube.channels().list(
        part="contentDetails", mine=True
    ).execute()
    uploads_id = (
        channel_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    )

    # Get video IDs
    playlist_response = youtube.playlistItems().list(
        part="snippet",
        playlistId=uploads_id,
        maxResults=min(max_results, 50),
    ).execute()

    video_ids = [
        item["snippet"]["resourceId"]["videoId"]
        for item in playlist_response.get("items", [])
    ]
    if not video_ids:
        return []

    # Fetch full stats
    videos_response = youtube.videos().list(
        part="snippet,statistics",
        id=",".join(video_ids),
    ).execute()

    results = []
    for item in videos_response.get("items", []):
        snippet = item["snippet"]
        stats = item["statistics"]
        results.append({
            "video_id": item["id"],
            "title": snippet.get("title", ""),
            "description": snippet.get("description", "")[:500],  # trim for LLM context
            "views": int(stats.get("viewCount", 0)),
            "likes": int(stats.get("likeCount", 0)),
            "comments": int(stats.get("commentCount", 0)),
            "published_at": snippet.get("publishedAt", ""),
        })

    return results
