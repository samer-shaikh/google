from fastapi import APIRouter, Depends, HTTPException, Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import os
import base64
import hashlib
import secrets
import requests as http_requests

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.youtube_account import YouTubeAccount
from app.agents.youtube_research_agent import YouTubeResearchAgent

router = APIRouter(prefix="/youtube", tags=["YouTube"])

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
]

GOOGLE_AUTH_URI  = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"


def _make_pkce_pair() -> tuple[str, str]:
    """
    Generate a PKCE code_verifier and its SHA-256 code_challenge.
    Required when Google Cloud OAuth client has PKCE enforced.
    """
    code_verifier = secrets.token_urlsafe(96)  # 128 chars, URL-safe
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return code_verifier, code_challenge


@router.get("/connect")
def connect_youtube(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    client_id    = os.getenv("GOOGLE_CLIENT_ID")
    redirect_uri = os.getenv("YOUTUBE_REDIRECT_URI")

    # Generate PKCE pair
    code_verifier, code_challenge = _make_pkce_pair()

    # Store verifier in session — needed for the callback token exchange
    request.session["youtube_code_verifier"] = code_verifier
    request.session["youtube_user_id"]       = current_user.id

    # Build the auth URL manually so we control every parameter
    scope = " ".join(SCOPES)
    params = (
        f"?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope={scope}"
        f"&access_type=offline"
        f"&prompt=consent"
        f"&state={current_user.id}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
    )
    auth_url = GOOGLE_AUTH_URI + params

    return {"auth_url": auth_url}


@router.get("/callback")
def youtube_callback(
    request: Request,
    code: str,
    state: str,
    db: Session = Depends(get_db),
):
    # Get user
    try:
        user_id = int(state)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Retrieve the PKCE verifier we stored in /connect
    code_verifier = request.session.get("youtube_code_verifier")
    if not code_verifier:
        raise HTTPException(
            status_code=400,
            detail="PKCE verifier missing from session. "
                   "Please start the flow again from /youtube/connect.",
        )

    client_id     = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri  = os.getenv("YOUTUBE_REDIRECT_URI")

    # Exchange code for tokens — include code_verifier to satisfy PKCE
    token_response = http_requests.post(
        GOOGLE_TOKEN_URI,
        data={
            "code":          code,
            "client_id":     client_id,
            "client_secret": client_secret,
            "redirect_uri":  redirect_uri,
            "grant_type":    "authorization_code",
            "code_verifier": code_verifier,   # ← PKCE verifier
        },
    )

    if token_response.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail=f"Token exchange failed: {token_response.text}",
        )

    token_data  = token_response.json()
    expires_in  = token_data.get("expires_in", 3600)
    expiry      = datetime.utcnow() + timedelta(seconds=expires_in)  # naive UTC — required by google-auth

    credentials = Credentials(
        token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        token_uri=GOOGLE_TOKEN_URI,
        client_id=client_id,
        client_secret=client_secret,
        expiry=expiry,
    )

    # Clean up session
    request.session.pop("youtube_code_verifier", None)
    request.session.pop("youtube_user_id", None)

    # Fetch channel info
    youtube  = build("youtube", "v3", credentials=credentials)
    response = youtube.channels().list(
        part="snippet,statistics", mine=True
    ).execute()

    if not response.get("items"):
        raise HTTPException(
            status_code=400,
            detail="No YouTube channel found for this Google account.",
        )

    channel = response["items"][0]

    # Upsert YouTubeAccount
    account = db.query(YouTubeAccount).filter(
        YouTubeAccount.user_id == user.id
    ).first()

    if account:
        account.channel_id    = channel["id"]
        account.channel_name  = channel["snippet"]["title"]
        account.access_token  = credentials.token
        account.refresh_token = credentials.refresh_token
        account.token_expiry  = expiry
    else:
        account = YouTubeAccount(
            user_id=      user.id,
            channel_id=   channel["id"],
            channel_name= channel["snippet"]["title"],
            access_token= credentials.token,
            refresh_token=credentials.refresh_token,
            token_expiry= expiry,
        )
        db.add(account)

    db.commit()
    db.refresh(account)

    return {
        "success":      True,
        "message":      "YouTube account connected successfully",
        "channel_name": account.channel_name,
        "channel_id":   account.channel_id,
    }


@router.get("/me")
def youtube_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = db.query(YouTubeAccount).filter(
        YouTubeAccount.user_id == current_user.id
    ).first()

    if not account:
        return {"connected": False}

    return {
        "connected":    True,
        "channel_name": account.channel_name,
        "channel_id":   account.channel_id,
    }


@router.post("/research")
def research_channel(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Fetches recent videos from the connected YouTube account
    and saves them to the youtube_videos table.
    """
    agent = YouTubeResearchAgent()
    return agent.run(user_id=current_user.id, db=db)
