"""
upload_workflow.py — Video Publishing Pipeline

Separate from the content generation workflow.
Runs AFTER content generation is complete.

Graph:
  load_generation → seo_agent → title_agent → description_agent →
  tags_agent → review_metadata (HITL) → upload_video → END

SEO lives here — not in the content generation workflow.
YouTube upload uses the Data API v3 directly (MCP fallback path planned).
"""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt

from app.graph.state import UploadState


# ── Node 1: Load generation from DB ─────────────────────────────

def load_generation_node(state: UploadState) -> dict:
    """
    Load the completed generation record from DB.
    Pulls script + thumbnail into state for SEO agents to use.
    """
    generation_id = state.get("generation_id")
    user_id = state.get("user_id")

    if not generation_id or not user_id:
        raise ValueError("generation_id and user_id are required to start upload workflow")

    from app.database import SessionLocal
    from app.models.generation import Generation

    db = SessionLocal()
    try:
        gen = db.query(Generation).filter(
            Generation.id == generation_id,
            Generation.user_id == user_id,
        ).first()

        if not gen:
            raise ValueError(f"Generation {generation_id} not found for user {user_id}")

        if gen.status != "completed":
            raise ValueError(
                f"Generation {generation_id} has status '{gen.status}'. "
                "Only completed generations can be published."
            )

        print(f"[load_generation_node] loaded generation '{gen.topic}'")
        return {
            "topic":     gen.topic,
            "script":    gen.script or "",
            "thumbnail": gen.thumbnail or "",
            "plan":      gen.plan or "normal",
        }
    finally:
        db.close()


# ── Node 2: SEO Title ────────────────────────────────────────────

def seo_title_node(state: UploadState) -> dict:
    """Generate an SEO-optimized YouTube title."""
    print("[seo_title_node] starting...")
    from app.services.qwen_service import generate_response
    from app.services.model_router import get_model

    prompt = f"""
You are a YouTube SEO expert.

Topic: {state["topic"]}

Script excerpt:
{(state.get("script") or "")[:1000]}

Generate ONE YouTube video title that:
- Is under 70 characters
- Contains the main keyword near the beginning
- Is compelling and click-worthy
- Matches the content accurately

Return ONLY the title text. No quotes, no explanation.
"""
    model = get_model(state.get("plan", "normal"), "seo")
    title = generate_response(prompt, model).strip().strip('"').strip("'")
    print(f"[seo_title_node] title: {title}")
    return {"seo_title": title}


# ── Node 3: SEO Description ──────────────────────────────────────

def seo_description_node(state: UploadState) -> dict:
    """Generate an SEO-optimized YouTube description."""
    print("[seo_description_node] starting...")
    from app.services.qwen_service import generate_response
    from app.services.model_router import get_model

    prompt = f"""
You are a YouTube SEO expert.

Topic: {state["topic"]}
Title: {state.get("seo_title", "")}

Script excerpt:
{(state.get("script") or "")[:1500]}

Write a YouTube video description that:
- Opens with the most important information (first 2 lines visible before "Show more")
- Is 150-200 words total
- Naturally includes relevant keywords
- Includes a call to action (like, subscribe, comment)
- Has a section for timestamps (write placeholder: [TIMESTAMPS])
- Has a section for links (write placeholder: [LINKS])

Return ONLY the description text.
"""
    model = get_model(state.get("plan", "normal"), "seo")
    description = generate_response(prompt, model).strip()
    print("[seo_description_node] done.")
    return {"seo_description": description}


# ── Node 4: Tags ─────────────────────────────────────────────────

def tags_node(state: UploadState) -> dict:
    """Generate YouTube tags and hashtags."""
    print("[tags_node] starting...")
    from app.services.qwen_service import generate_response
    from app.services.model_router import get_model
    import json, re

    prompt = f"""
You are a YouTube SEO expert.

Topic: {state["topic"]}
Title: {state.get("seo_title", "")}

Generate YouTube tags and hashtags for this video.

Return ONLY a valid JSON object with exactly these fields:
{{
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5", "tag6", "tag7", "tag8", "tag9", "tag10", "tag11", "tag12", "tag13", "tag14", "tag15"],
  "hashtags": ["#hashtag1", "#hashtag2", "#hashtag3", "#hashtag4", "#hashtag5"],
  "category": "Education"
}}

Rules:
- tags: exactly 15 strings, no # symbol, mix of broad and specific
- hashtags: exactly 5 strings, each starting with #
- category: one YouTube category name that fits this content
"""
    model = get_model(state.get("plan", "normal"), "seo")
    raw = generate_response(prompt, model)

    try:
        cleaned = re.sub(r"```[a-z]*", "", raw).strip().strip("`").strip()
        data = json.loads(cleaned)
        return {
            "seo_tags":      data.get("tags", []),
            "seo_hashtags":  data.get("hashtags", []),
            "seo_category":  data.get("category", "Education"),
        }
    except Exception as e:
        print(f"[tags_node] JSON parse failed: {e} — using fallback")
        return {
            "seo_tags":     [state["topic"]],
            "seo_hashtags": [],
            "seo_category": "Education",
        }


# ── Node 5: HITL — Metadata review ──────────────────────────────

def review_metadata_node(state: UploadState) -> dict:
    """
    Pause and show the user all generated SEO metadata for review.
    User can approve or send back corrections.
    """
    print("[review_metadata_node] pausing for user review...")

    approved = interrupt({
        "type":             "metadata_review",
        "seo_title":        state.get("seo_title", ""),
        "seo_description":  state.get("seo_description", ""),
        "seo_tags":         state.get("seo_tags", []),
        "seo_hashtags":     state.get("seo_hashtags", []),
        "seo_category":     state.get("seo_category", ""),
        "privacy_status":   state.get("privacy_status", "private"),
        "message":          "Review SEO metadata. Approve to upload to YouTube.",
    })

    print(f"[review_metadata_node] resumed — approved={approved}")
    return {"seo_approved": approved}


# ── Node 6: Upload to YouTube ────────────────────────────────────

def upload_video_node(state: UploadState) -> dict:
    """
    Upload the video to YouTube using the Data API v3.

    MCP path (future): if a YouTube MCP server is connected,
    delegate to it instead of calling the API directly.

    Current implementation: YouTube Data API v3 via google-api-python-client.
    Requires the user to have a connected YouTube account (oauth tokens in DB).
    """
    print("[upload_video_node] starting...")

    if not state.get("seo_approved"):
        print("[upload_video_node] not approved — skipping upload")
        return {"upload_status": "cancelled"}

    user_id = state.get("user_id")
    if not user_id:
        return {"upload_status": "failed", "upload_error": "user_id missing from state"}

    from app.database import SessionLocal
    from app.models.youtube_account import YouTubeAccount
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request as GoogleRequest
    from googleapiclient.discovery import build
    from datetime import datetime
    import os

    db = SessionLocal()
    try:
        account = db.query(YouTubeAccount).filter(
            YouTubeAccount.user_id == user_id
        ).first()

        if not account:
            return {
                "upload_status": "failed",
                "upload_error":  "No YouTube account connected. Connect via /youtube/connect first.",
            }

        # Build credentials + refresh if expired
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

        youtube = build("youtube", "v3", credentials=credentials)

        # Build video metadata for the API call
        # NOTE: actual video file upload requires a file path/bytes.
        # For now this node prepares and validates the metadata.
        # Full binary upload will be added when video file handling is implemented.
        video_metadata = {
            "snippet": {
                "title":       state.get("seo_title", state.get("topic", "")),
                "description": state.get("seo_description", ""),
                "tags":        state.get("seo_tags", []),
                "categoryId":  "27",  # Education — will map from seo_category later
            },
            "status": {
                "privacyStatus":           state.get("privacy_status", "private"),
                "selfDeclaredMadeForKids": False,
            },
        }

        print(f"[upload_video_node] metadata prepared: {video_metadata['snippet']['title']}")
        print("[upload_video_node] NOTE: video file upload requires file path — metadata only for now")

        # TODO: When video file upload is ready, use:
        # from googleapiclient.http import MediaFileUpload
        # media = MediaFileUpload(video_file_path, chunksize=-1, resumable=True)
        # request = youtube.videos().insert(part="snippet,status", body=video_metadata, media_body=media)
        # response = request.execute()
        # return {"youtube_video_id": response["id"], "upload_status": "uploaded"}

        return {
            "upload_status":    "metadata_ready",
            "youtube_video_id": "",
        }

    except Exception as e:
        print(f"[upload_video_node] error: {e}")
        return {"upload_status": "failed", "upload_error": str(e)}
    finally:
        db.close()


# ── Conditional edge ─────────────────────────────────────────────

def check_seo_approval(state: UploadState) -> str:
    return "approved" if state.get("seo_approved") is True else "rejected"


def handle_upload_rejection_node(state: UploadState) -> dict:
    print("[handle_upload_rejection_node] user rejected metadata")
    return {"upload_status": "cancelled"}


# ── Graph construction ───────────────────────────────────────────

def _build_upload_graph(checkpointer: MemorySaver):
    builder = StateGraph(UploadState)

    builder.add_node("load_generation",         load_generation_node)
    builder.add_node("seo_title",               seo_title_node)
    builder.add_node("seo_description",         seo_description_node)
    builder.add_node("tags",                    tags_node)
    builder.add_node("review_metadata",         review_metadata_node)
    builder.add_node("upload_video",            upload_video_node)
    builder.add_node("handle_upload_rejection", handle_upload_rejection_node)

    builder.set_entry_point("load_generation")
    builder.add_edge("load_generation", "seo_title")
    builder.add_edge("seo_title",       "seo_description")
    builder.add_edge("seo_description", "tags")
    builder.add_edge("tags",            "review_metadata")

    builder.add_conditional_edges(
        "review_metadata",
        check_seo_approval,
        {"approved": "upload_video", "rejected": "handle_upload_rejection"},
    )

    builder.add_edge("upload_video",            END)
    builder.add_edge("handle_upload_rejection", END)

    return builder.compile(checkpointer=checkpointer)


# ── Singleton ────────────────────────────────────────────────────

import sys as _sys
_MODULE = _sys.modules[__name__]

if not hasattr(_MODULE, "_upload_checkpointer"):
    _MODULE._upload_checkpointer = MemorySaver()

if not hasattr(_MODULE, "_upload_graph"):
    _MODULE._upload_graph = _build_upload_graph(_MODULE._upload_checkpointer)

upload_checkpointer: MemorySaver = _MODULE._upload_checkpointer
upload_graph = _MODULE._upload_graph
