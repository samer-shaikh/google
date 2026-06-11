"""
upload_workflow.py — Video Publishing Pipeline

Graph:
  load_generation → seo_title → seo_description → tags →
  review_metadata (HITL) → upload_video → upload_thumbnail →
  save_upload_result → END
"""
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt
from datetime import datetime, timezone

from app.graph.state import UploadState
from app.graph.checkpointer import get_checkpointer


# ── Helper: load creator profile ─────────────────────────────────────────────

def _get_creator_profile(user_id: int) -> dict:
    try:
        from app.memory import get_creator_memory_service
        return get_creator_memory_service().get_context_for_agents(user_id)
    except Exception:
        return {}


def _get_performing_keywords(user_id: int, niche: str) -> list[str]:
    try:
        from app.mcp.elastic.tools import search_performing_keywords
        results = search_performing_keywords(user_id=user_id, niche=niche, limit=10)
        return [r.get("keyword", "") for r in results if r.get("keyword")]
    except Exception:
        return []


# ── Node 1: load_generation ───────────────────────────────────────────────────

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


# ── Node 2: seo_title ─────────────────────────────────────────────────────────

def seo_title_node(state: UploadState) -> dict:
    print("[seo_title_node] starting...")
    from app.services.llm_provider import generate_response
    from app.services.model_router import get_model
    from app.agents.research_agent import _profile_context

    user_id = state.get("user_id")
    creator_profile = _get_creator_profile(user_id) if user_id else {}

    niche = creator_profile.get("creator_niche", "")
    performing_keywords = _get_performing_keywords(user_id, niche) if user_id and niche else []
    keywords_ctx = f"\nHigh-performing keywords for this channel: {', '.join(performing_keywords)}" if performing_keywords else ""

    profile_ctx = _profile_context(creator_profile)
    title_style = creator_profile.get("title_style", {})
    title_style_str = title_style.get("style", "neutral") if isinstance(title_style, dict) else str(title_style)

    prompt = f"""
You are a YouTube SEO expert working for a specific creator.

{profile_ctx}
{keywords_ctx}

Topic: {state["topic"]}
Script excerpt: {(state.get("script") or "")[:800]}
Creator's title style: {title_style_str}

Generate ONE YouTube video title that:
- Is under 70 characters
- Contains the main keyword near the beginning
- Matches the creator's title style exactly
- Is compelling and click-worthy

Return ONLY the title text. No quotes, no explanation, no markdown.
""".strip()

    model = get_model(state.get("plan", "normal"), "seo")
    title = generate_response(prompt, model).strip().strip('"').strip("'")
    print(f"[seo_title_node] title: {title}")
    return {"seo_title": title}


# ── Node 3: seo_description ───────────────────────────────────────────────────

def seo_description_node(state: UploadState) -> dict:
    print("[seo_description_node] starting...")
    from app.services.llm_provider import generate_response
    from app.services.model_router import get_model
    from app.agents.research_agent import _profile_context
    from app.agents.utils import load_prompt

    user_id = state.get("user_id")
    creator_profile = _get_creator_profile(user_id) if user_id else {}
    profile_ctx = _profile_context(creator_profile)

    desc_style = creator_profile.get("description_style", {})
    desc_style_str = desc_style.get("style", "minimal") if isinstance(desc_style, dict) else str(desc_style)

    audience = creator_profile.get("audience", {})
    audience_type = audience.get("audience_type", "general viewers") if isinstance(audience, dict) else "general viewers"
    main_topics = creator_profile.get("main_topics", [])

    try:
        prompt_template = load_prompt("seo.txt")
        prompt = prompt_template.format(
            profile_ctx=profile_ctx,
            topic=state["topic"],
            script=(state.get("script") or "")[:1500],
            audience_type=audience_type,
            main_topics=", ".join(main_topics) if main_topics else state["topic"],
        )
        prompt += "\n\nIMPORTANT: Return ONLY the Description section. No titles, no tags, no hashtags."
    except Exception:
        prompt = f"""
You are a YouTube SEO expert.

Topic: {state["topic"]}
Title: {state.get("seo_title", "")}
Description style: {desc_style_str}
Script: {(state.get("script") or "")[:1500]}

Write a YouTube description (150-200 words). Return ONLY the description text.
""".strip()

    model = get_model(state.get("plan", "normal"), "seo")
    description = generate_response(prompt, model).strip()
    print("[seo_description_node] done.")
    return {"seo_description": description}


# ── Node 4: tags ──────────────────────────────────────────────────────────────

def tags_node(state: UploadState) -> dict:
    print("[tags_node] starting...")
    from app.services.llm_provider import generate_response
    from app.services.model_router import get_model
    import json, re

    user_id = state.get("user_id")
    creator_profile = _get_creator_profile(user_id) if user_id else {}

    niche = creator_profile.get("creator_niche", "")
    main_topics = creator_profile.get("main_topics", [])
    performing_keywords = _get_performing_keywords(user_id, niche) if user_id and niche else []

    keywords_hint = ""
    if performing_keywords:
        keywords_hint = f"\nInclude these high-performing keywords in the tags where relevant: {', '.join(performing_keywords[:8])}"

    audience = creator_profile.get("audience", {})
    audience_level = audience.get("audience_level", "beginner") if isinstance(audience, dict) else "beginner"

    prompt = f"""
You are a YouTube SEO expert.

Creator niche: {niche or state["topic"]}
Main topics: {", ".join(main_topics) if main_topics else state["topic"]}
Audience level: {audience_level}
Video topic: {state["topic"]}
Video title: {state.get("seo_title", "")}
{keywords_hint}

Return ONLY a valid JSON object:
{{
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5", "tag6", "tag7", "tag8", "tag9", "tag10", "tag11", "tag12", "tag13", "tag14", "tag15"],
  "hashtags": ["#hashtag1", "#hashtag2", "#hashtag3", "#hashtag4", "#hashtag5"],
  "category": "Education"
}}

Rules:
- tags: exactly 15 strings, no # symbol
- hashtags: exactly 5, each starting with #
- category: one YouTube category (Education / Science & Technology / Entertainment / Howto & Style)
""".strip()

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
        fallback_tags = [state["topic"]] + main_topics[:5] + performing_keywords[:5]
        return {
            "seo_tags":     fallback_tags[:15],
            "seo_hashtags": [],
            "seo_category": "Education",
        }


# ── Node 5: review_metadata (HITL) ───────────────────────────────────────────

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


# ── Node 6: upload_video ──────────────────────────────────────────────────────

def upload_video_node(state: UploadState) -> dict:
    print("[upload_video_node] starting...")

    if not state.get("seo_approved"):
        return {"upload_status": "cancelled"}

    user_id         = state.get("user_id")
    video_file_path = state.get("video_file_path", "")

    if not user_id:
        return {"upload_status": "failed", "upload_error": "user_id missing from state"}

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

    category_name = state.get("seo_category", "Education")
    category_id   = CATEGORY_MAP.get(category_name, "27")

    db = SessionLocal()
    try:
        provider = get_youtube_provider(user_id=user_id, db=db)
        result   = provider.upload_video(
            video_file_path=video_file_path,
            title=          state.get("seo_title", state.get("topic", ""))[:100],
            description=    state.get("seo_description", ""),
            tags=           state.get("seo_tags", []),
            category_id=    category_id,
            privacy_status= state.get("privacy_status", "private"),
        )
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


# ── Node 7: upload_thumbnail ──────────────────────────────────────────────────

def upload_thumbnail_node(state: UploadState) -> dict:
    print("[upload_thumbnail_node] starting...")

    video_id       = state.get("youtube_video_id", "")
    thumbnail_path = state.get("thumbnail_file_path", "")
    user_id        = state.get("user_id")

    if not video_id:
        print("[upload_thumbnail_node] no video_id — skipping")
        return {"thumbnail_status": "skipped", "thumbnail_uploaded": False}

    if not thumbnail_path:
        print("[upload_thumbnail_node] no thumbnail_file_path — skipping")
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
        result   = provider.upload_thumbnail(video_id=video_id, thumbnail_path=thumbnail_path)
        status   = result.get("thumbnail_status", "failed")

        print(f"[upload_thumbnail_node] result: {status}")

        # ── "skipped_unverified" is a SOFT success ──────────────────────────
        # The video was already uploaded. Treat this as non-fatal so
        # save_upload_result_node still records the upload as successful.
        is_success = status in ("uploaded", "skipped_unverified", "skipped")

        return {
            "thumbnail_status":   status,
            "thumbnail_uploaded": status == "uploaded",
            "thumbnail_error":    result.get("error"),
            # Preserve upload_status from video node if thumbnail just skipped
            **({"upload_status": "uploaded"} if is_success and state.get("upload_status") == "uploaded" else {}),
        }
    except Exception as e:
        # Never let thumbnail errors kill the upload record
        print(f"[upload_thumbnail_node] error (non-fatal): {e}")
        return {
            "thumbnail_status":   "failed",
            "thumbnail_uploaded": False,
            "thumbnail_error":    str(e),
        }
    finally:
        db.close()


# ── Node 8: save_upload_result ────────────────────────────────────────────────

def save_upload_result_node(state: UploadState) -> dict:
    print("[save_upload_result_node] saving upload result...")

    from app.database import SessionLocal
    from app.services.upload_service import (
        create_upload_record, complete_upload_record,
        fail_upload_record, cancel_upload_record,
    )
    from datetime import datetime as _datetime, timezone as _timezone

    upload_status = state.get("upload_status", "failed")
    user_id       = state.get("user_id")

    db = SessionLocal()
    record = None
    try:
        record = create_upload_record(
            user_id=         user_id,
            generation_id=   state.get("generation_id"),
            seo_title=       state.get("seo_title", ""),
            seo_description= state.get("seo_description", ""),
            seo_tags=        state.get("seo_tags", []),
            seo_hashtags=    state.get("seo_hashtags", []),
            seo_category=    state.get("seo_category", ""),
            privacy_status=  state.get("privacy_status", "private"),
            db=db,
        )

        published_at = _datetime.now(_timezone.utc).isoformat()

        if upload_status in ("uploaded", "metadata_ready"):
            complete_upload_record(
                record_id=         record.id,
                youtube_video_id=  state.get("youtube_video_id",  ""),
                youtube_video_url= state.get("youtube_video_url", ""),
                thumbnail_status=  state.get("thumbnail_status",  "skipped"),
                provider_used=     state.get("provider_used",     "api"),
                upload_status=     upload_status,
                db=db,
            )
        elif upload_status == "cancelled":
            cancel_upload_record(record.id, db)
            published_at = None
        else:
            fail_upload_record(record.id, state.get("upload_error", "unknown error"), db)
            published_at = None

        print(f"[save_upload_result_node] record {record.id} saved as {upload_status}")

    except Exception as e:
        print(f"[save_upload_result_node] error: {e}")
        return {"upload_record_id": None, "published_at": None}
    finally:
        db.close()

    # Auto-delete temp files after successful upload
    if upload_status in ("uploaded", "metadata_ready"):
        for path_key in ("video_file_path", "thumbnail_file_path"):
            file_path = state.get(path_key, "")
            if file_path:
                try:
                    import os
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        print(f"[save_upload_result_node] deleted temp file: {file_path}")
                except Exception as cleanup_err:
                    print(f"[save_upload_result_node] cleanup warning (non-fatal): {cleanup_err}")

    if user_id and upload_status == "uploaded":
        try:
            from app.mcp.mongodb.tools import upsert_one
            upsert_one(
                "content_pieces",
                {"generation_id": state.get("generation_id")},
                {"$set": {
                    "youtube_video_id": state.get("youtube_video_id", ""),
                    "upload_record_id": record.id,
                    "seo.title":        state.get("seo_title", ""),
                    "seo.tags":         state.get("seo_tags", []),
                    "seo.category":     state.get("seo_category", ""),
                    "updated_at":       _datetime.now(_timezone.utc),
                }},
            )
            from app.memory import get_creator_memory_service
            get_creator_memory_service().increment_uploads(user_id)
            print(f"[save_upload_result_node] MongoDB content_piece updated")
        except Exception as e:
            print(f"[save_upload_result_node] MongoDB update warning (non-fatal): {e}")

    return {
        "upload_record_id": record.id if record else None,
        "published_at":     published_at,
    }


# ── Conditional edges ─────────────────────────────────────────────────────────

def check_seo_approval(state: UploadState) -> str:
    return "approved" if state.get("seo_approved") is True else "rejected"


def handle_upload_rejection_node(state: UploadState) -> dict:
    print("[handle_upload_rejection_node] user rejected metadata")
    return {"upload_status": "cancelled"}


# ── Graph construction ────────────────────────────────────────────────────────

def _build_upload_graph(checkpointer):
    builder = StateGraph(UploadState)

    builder.add_node("load_generation",         load_generation_node)
    builder.add_node("seo_title",               seo_title_node)
    builder.add_node("seo_description",         seo_description_node)
    builder.add_node("tags",                    tags_node)
    builder.add_node("review_metadata",         review_metadata_node)
    builder.add_node("handle_upload_rejection", handle_upload_rejection_node)
    builder.add_node("upload_video",            upload_video_node)
    builder.add_node("upload_thumbnail",        upload_thumbnail_node)
    builder.add_node("save_upload_result",      save_upload_result_node)

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

    builder.add_edge("upload_video",            "upload_thumbnail")
    builder.add_edge("upload_thumbnail",        "save_upload_result")
    builder.add_edge("save_upload_result",      END)
    builder.add_edge("handle_upload_rejection", "save_upload_result")

    return builder.compile(checkpointer=checkpointer)


# ── Singleton ─────────────────────────────────────────────────────────────────

import sys as _sys
_MODULE = _sys.modules[__name__]

upload_graph = None


def init_upload_graph():
    if not hasattr(_MODULE, "_upload_graph") or _MODULE._upload_graph is None:
        _MODULE._upload_graph = _build_upload_graph(get_checkpointer())
        print("[upload_workflow] upload graph compiled")
    import app.graph.upload_workflow as _self
    _self.upload_graph = _MODULE._upload_graph
    return _MODULE._upload_graph
