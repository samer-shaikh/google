"""
upload_workflow.py — Video Publishing Pipeline

Graph:
  load_generation → seo_title → seo_description → tags →
  review_metadata (HITL) → upload_thumbnail → upload_video →
  save_upload_result → END

All existing nodes are preserved unchanged.
Three new nodes added: upload_thumbnail, upload_video (real), save_upload_result.
Provider abstraction: workflow calls get_youtube_provider() — works with
Data API or MCP depending on environment configuration.
"""
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt
from datetime import datetime, timezone

from app.graph.state import UploadState
from app.graph.checkpointer import get_checkpointer


# ══════════════════════════════════════════════════════════════════
# EXISTING NODES — unchanged
# ══════════════════════════════════════════════════════════════════

def load_generation_node(state: UploadState) -> dict:
    generation_id = state.get("generation_id")
    user_id       = state.get("user_id")

    if not generation_id or not user_id:
        raise ValueError("generation_id and user_id are required")

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


def seo_title_node(state: UploadState) -> dict:
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


def seo_description_node(state: UploadState) -> dict:
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


def tags_node(state: UploadState) -> dict:
    print("[tags_node] starting...")
    from app.services.qwen_service import generate_response
    from app.services.model_router import get_model
    import json, re

    prompt = f"""
You are a YouTube SEO expert.

Topic: {state["topic"]}
Title: {state.get("seo_title", "")}

Return ONLY a valid JSON object with exactly these fields:
{{
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5", "tag6", "tag7", "tag8", "tag9", "tag10", "tag11", "tag12", "tag13", "tag14", "tag15"],
  "hashtags": ["#hashtag1", "#hashtag2", "#hashtag3", "#hashtag4", "#hashtag5"],
  "category": "Education"
}}
"""
    model = get_model(state.get("plan", "normal"), "seo")
    raw   = generate_response(prompt, model)

    try:
        cleaned = re.sub(r"```[a-z]*", "", raw).strip().strip("`").strip()
        data    = json.loads(cleaned)
        return {
            "seo_tags":     data.get("tags",     []),
            "seo_hashtags": data.get("hashtags", []),
            "seo_category": data.get("category", "Education"),
        }
    except Exception as e:
        print(f"[tags_node] JSON parse failed: {e} — using fallback")
        return {"seo_tags": [state["topic"]], "seo_hashtags": [], "seo_category": "Education"}


def review_metadata_node(state: UploadState) -> dict:
    print("[review_metadata_node] pausing for user review...")

    approved = interrupt({
        "type":            "metadata_review",
        "seo_title":       state.get("seo_title", ""),
        "seo_description": state.get("seo_description", ""),
        "seo_tags":        state.get("seo_tags", []),
        "seo_hashtags":    state.get("seo_hashtags", []),
        "seo_category":    state.get("seo_category", ""),
        "privacy_status":  state.get("privacy_status", "private"),
        "message":         "Review SEO metadata. Approve to upload to YouTube.",
    })

    print(f"[review_metadata_node] resumed — approved={approved}")
    return {"seo_approved": approved}


# ══════════════════════════════════════════════════════════════════
# NEW NODE A: upload_thumbnail_node
# ══════════════════════════════════════════════════════════════════

def upload_thumbnail_node(state: UploadState) -> dict:
    """
    Upload the AI-generated thumbnail concept to YouTube.

    The thumbnail field in state contains the text description/prompt
    generated by the content workflow's ThumbnailAgent.

    For actual image upload, the thumbnail must be a real image file.
    If no thumbnail_file_path is provided in state, this node skips
    gracefully and marks thumbnail_status as "skipped".

    The node runs AFTER upload_video because YouTube requires a
    video_id before a thumbnail can be attached.
    """
    print("[upload_thumbnail_node] starting...")

    video_id        = state.get("youtube_video_id", "")
    thumbnail_path  = state.get("thumbnail_file_path", "")  # optional path to image file
    user_id         = state.get("user_id")

    # If no video was uploaded yet, skip
    if not video_id:
        print("[upload_thumbnail_node] no video_id — skipping thumbnail upload")
        return {"thumbnail_status": "skipped", "thumbnail_uploaded": False}

    # If no thumbnail image file provided, skip gracefully
    if not thumbnail_path:
        print("[upload_thumbnail_node] no thumbnail_file_path — skipping thumbnail upload")
        return {
            "thumbnail_status":   "skipped",
            "thumbnail_uploaded": False,
            "thumbnail_error":    "No thumbnail_file_path provided",
        }

    from app.database import SessionLocal
    from app.youtube_provider import get_youtube_provider

    db = SessionLocal()
    try:
        provider = get_youtube_provider(user_id=user_id, db=db)
        result   = provider.upload_thumbnail(
            video_id=       video_id,
            thumbnail_path= thumbnail_path,
        )

        print(f"[upload_thumbnail_node] result: {result}")
        return {
            "thumbnail_status":   result.get("thumbnail_status", "failed"),
            "thumbnail_uploaded": result.get("thumbnail_status") == "uploaded",
            "thumbnail_error":    result.get("error"),
        }
    except Exception as e:
        print(f"[upload_thumbnail_node] error: {e}")
        return {
            "thumbnail_status":   "failed",
            "thumbnail_uploaded": False,
            "thumbnail_error":    str(e),
        }
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════
# NEW NODE B: upload_video_node (real implementation)
# ══════════════════════════════════════════════════════════════════

def upload_video_node(state: UploadState) -> dict:
    """
    Upload the video file to YouTube using the provider abstraction.

    Requires:
      - seo_approved == True (from review_metadata HITL)
      - video_file_path in state (absolute path to .mp4 / .mov)
      - user_id with a connected YouTube account

    Returns youtube_video_id, youtube_video_url, upload_status, upload_error.

    If video_file_path is missing, returns upload_status="metadata_ready"
    so the demo flow still works without an actual video file.
    """
    print("[upload_video_node] starting...")

    if not state.get("seo_approved"):
        return {"upload_status": "cancelled"}

    user_id         = state.get("user_id")
    video_file_path = state.get("video_file_path", "")

    if not user_id:
        return {"upload_status": "failed", "upload_error": "user_id missing from state"}

    # Demo mode: no video file provided — return metadata_ready so the
    # rest of the workflow (thumbnail, save) still runs correctly
    if not video_file_path:
        print("[upload_video_node] no video_file_path — demo mode (metadata only)")
        return {
            "youtube_video_id":  "",
            "youtube_video_url": "",
            "upload_status":     "metadata_ready",
            "upload_error":      None,
            "provider_used":     "none",
        }

    from app.database import SessionLocal
    from app.youtube_provider import get_youtube_provider
    from app.youtube_provider.youtube_api_provider import CATEGORY_MAP

    # Map category name → ID (default to Education = 27)
    category_name = state.get("seo_category", "Education")
    category_id   = CATEGORY_MAP.get(category_name, "27")

    db = SessionLocal()
    try:
        provider = get_youtube_provider(user_id=user_id, db=db)
        result   = provider.upload_video(
            video_file_path=video_file_path,
            title=          state.get("seo_title",       state.get("topic", ""))[:100],
            description=    state.get("seo_description", ""),
            tags=           state.get("seo_tags",        []),
            category_id=    category_id,
            privacy_status= state.get("privacy_status",  "private"),
        )

        # Determine which provider was used
        provider_name = "mcp" if hasattr(provider, "mcp_url") else "api"

        print(f"[upload_video_node] result: {result.get('upload_status')}")
        return {
            "youtube_video_id":  result.get("youtube_video_id",  ""),
            "youtube_video_url": result.get("youtube_video_url", ""),
            "upload_status":     result.get("upload_status",     "failed"),
            "upload_error":      result.get("error"),
            "provider_used":     provider_name,
        }

    except Exception as e:
        print(f"[upload_video_node] error: {e}")
        return {
            "youtube_video_id":  "",
            "youtube_video_url": "",
            "upload_status":     "failed",
            "upload_error":      str(e),
            "provider_used":     "unknown",
        }
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════
# NEW NODE C: save_upload_result_node
# ══════════════════════════════════════════════════════════════════

def save_upload_result_node(state: UploadState) -> dict:
    """
    Save the complete upload result to upload_records table.
    Runs after both upload_thumbnail and upload_video complete.
    Always runs — even if upload failed — so we have a full audit trail.
    """
    print("[save_upload_result_node] saving upload result...")

    from app.database import SessionLocal
    from app.services.upload_service import (
        create_upload_record,
        complete_upload_record,
        fail_upload_record,
        cancel_upload_record,
    )

    upload_status = state.get("upload_status", "failed")

    db = SessionLocal()
    try:
        # Create the record
        record = create_upload_record(
            user_id=         state.get("user_id"),
            generation_id=   state.get("generation_id"),
            seo_title=       state.get("seo_title", ""),
            seo_description= state.get("seo_description", ""),
            seo_tags=        state.get("seo_tags", []),
            seo_hashtags=    state.get("seo_hashtags", []),
            seo_category=    state.get("seo_category", ""),
            privacy_status=  state.get("privacy_status", "private"),
            db=db,
        )

        published_at = datetime.now(timezone.utc).isoformat()

        if upload_status in ("uploaded", "metadata_ready"):
            complete_upload_record(
                record_id=        record.id,
                youtube_video_id=  state.get("youtube_video_id",  ""),
                youtube_video_url= state.get("youtube_video_url", ""),
                thumbnail_status=  state.get("thumbnail_status",  "skipped"),
                provider_used=     state.get("provider_used",     "api"),
                db=db,
            )
        elif upload_status == "cancelled":
            cancel_upload_record(record.id, db)
            published_at = None
        else:
            fail_upload_record(record.id, state.get("upload_error", "unknown error"), db)
            published_at = None

        print(f"[save_upload_result_node] record {record.id} saved as {upload_status}")
        return {
            "upload_record_id": record.id,
            "published_at":     published_at,
        }

    except Exception as e:
        print(f"[save_upload_result_node] error saving record: {e}")
        return {"upload_record_id": None, "published_at": None}
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════
# Conditional edges
# ══════════════════════════════════════════════════════════════════

def check_seo_approval(state: UploadState) -> str:
    return "approved" if state.get("seo_approved") is True else "rejected"


def handle_upload_rejection_node(state: UploadState) -> dict:
    print("[handle_upload_rejection_node] user rejected metadata")
    return {"upload_status": "cancelled"}


# ══════════════════════════════════════════════════════════════════
# Graph construction
# New graph: ... → review_metadata → upload_video → upload_thumbnail
#            → save_upload_result → END
# ══════════════════════════════════════════════════════════════════

def _build_upload_graph(checkpointer):
    builder = StateGraph(UploadState)

    # Existing nodes
    builder.add_node("load_generation",         load_generation_node)
    builder.add_node("seo_title",               seo_title_node)
    builder.add_node("seo_description",         seo_description_node)
    builder.add_node("tags",                    tags_node)
    builder.add_node("review_metadata",         review_metadata_node)
    builder.add_node("handle_upload_rejection", handle_upload_rejection_node)

    # New nodes
    builder.add_node("upload_video",            upload_video_node)
    builder.add_node("upload_thumbnail",        upload_thumbnail_node)
    builder.add_node("save_upload_result",      save_upload_result_node)

    # Edges — existing
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

    # Edges — new
    # upload_video first (need video_id before thumbnail)
    builder.add_edge("upload_video",       "upload_thumbnail")
    builder.add_edge("upload_thumbnail",   "save_upload_result")
    builder.add_edge("save_upload_result", END)

    # Rejection path also saves a record
    builder.add_edge("handle_upload_rejection", "save_upload_result")

    return builder.compile(checkpointer=checkpointer)


# ── Singleton — built once after FastAPI lifespan startup ──────

import sys as _sys
_MODULE = _sys.modules[__name__]

upload_graph = None   # set by init_upload_graph() in main.py


def init_upload_graph():
    """
    Build and cache the upload workflow graph.
    Called once from FastAPI lifespan startup AFTER checkpointer is ready.
    """
    if not hasattr(_MODULE, "_upload_graph") or _MODULE._upload_graph is None:
        _MODULE._upload_graph = _build_upload_graph(get_checkpointer())
        print("[upload_workflow] upload graph compiled")

    import app.graph.upload_workflow as _self
    _self.upload_graph = _MODULE._upload_graph
    return _MODULE._upload_graph
