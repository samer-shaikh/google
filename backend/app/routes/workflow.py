import uuid
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional

from langgraph.types import Command
from sqlalchemy.orm import Session

from app.graph.workflow import graph
from app.graph.upload_workflow import upload_graph
from app.models.plan import Plan
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.database import get_db
from app.services.generation_service import (
    create_generation,
    get_user_generations,
    get_generation_by_id,
    get_generation_by_workflow_thread,
)

router = APIRouter(prefix="/workflow", tags=["workflow"])


# ── Request models ────────────────────────────────────────────────

class WorkflowStartRequest(BaseModel):
    topic: str
    plan: Plan = Plan.normal

class WorkflowResumeRequest(BaseModel):
    thread_id: str
    approved: bool

class IdeaSelectRequest(BaseModel):
    thread_id: str
    selected_idea: str

class UploadStartRequest(BaseModel):
    generation_id: int
    privacy_status: str = "private"   # private | unlisted | public
    plan: Plan = Plan.normal

class UploadReviewRequest(BaseModel):
    thread_id: str
    approved: bool
    # Optional overrides — user can edit SEO before approving
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    seo_tags: Optional[list[str]] = None
    privacy_status: Optional[str] = None


# ── Helper ────────────────────────────────────────────────────────

def _paused_at(state) -> str:
    if state and state.next:
        return list(state.next)[0]
    return ""


# ══════════════════════════════════════════════════════════════════
# CONTENT GENERATION WORKFLOW
# Research → Ideas → Script → Thumbnail → Save
# (SEO removed — it lives in the Upload Workflow)
# ══════════════════════════════════════════════════════════════════

@router.post("/run")
def run_workflow(
    data: WorkflowStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Start content generation pipeline.
    Creates a pending generation record, runs Research,
    then pauses at human_approval (HITL #1).
    """
    thread_id = str(uuid.uuid4())
    config    = {"configurable": {"thread_id": thread_id}}

    generation = create_generation(
        user_id=current_user.id,
        topic=data.topic,
        workflow_thread_id=thread_id,
        plan=data.plan.value,
        db=db,
    )

    result = graph.invoke(
        {
            "topic":         data.topic,
            "plan":          data.plan.value,
            "user_id":       current_user.id,
            "generation_id": generation.id,
        },
        config=config,
    )

    state  = graph.get_state(config)
    paused = _paused_at(state)

    return {
        "thread_id":     thread_id,
        "generation_id": generation.id,
        "status":        "awaiting_approval" if paused else "completed",
        "paused_at":     paused,
        "research":      result.get("research", ""),
    }


@router.post("/resume")
def resume_workflow(
    data: WorkflowResumeRequest,
    db: Session = Depends(get_db),
):
    """
    HITL #1 — Research approval.
    approved=true  → continues to Ideas → pauses at idea_selection.
    approved=false → marks generation failed, ends workflow.
    """
    config = {"configurable": {"thread_id": data.thread_id}}

    state = graph.get_state(config)
    if not state or not state.values:
        raise HTTPException(
            status_code=404,
            detail=f"Thread '{data.thread_id}' not found. Start a new run."
        )
    if not state.next:
        raise HTTPException(status_code=400, detail="Workflow is not paused.")

    paused = _paused_at(state)
    if paused != "human_approval":
        raise HTTPException(
            status_code=400,
            detail=f"Graph is paused at '{paused}', not 'human_approval'."
        )

    result = graph.invoke(Command(resume=data.approved), config=config)

    if not data.approved:
        return {
            "thread_id": data.thread_id,
            "status":    "rejected",
            "message":   "Workflow rejected. Generation marked as failed.",
        }

    new_state  = graph.get_state(config)
    paused_now = _paused_at(new_state)
    ideas      = result.get("ideas", [])
    ideas      = ideas if isinstance(ideas, list) else []

    return {
        "thread_id": data.thread_id,
        "status":    "awaiting_idea_selection" if paused_now == "idea_selection" else "completed",
        "paused_at": paused_now,
        "ideas":     ideas,
        "research":  result.get("research", ""),
    }


@router.post("/select-idea")
def select_idea(
    data: IdeaSelectRequest,
    db: Session = Depends(get_db),
):
    """
    HITL #2 — Idea selection.
    Runs Script → Thumbnail → Save → END.
    Returns completed generation (no SEO — that's in the upload workflow).
    """
    config = {"configurable": {"thread_id": data.thread_id}}

    state = graph.get_state(config)
    if not state or not state.values:
        raise HTTPException(status_code=404, detail=f"Thread '{data.thread_id}' not found.")
    if not state.next:
        raise HTTPException(status_code=400, detail="Workflow is not paused.")

    paused = _paused_at(state)
    if paused != "idea_selection":
        raise HTTPException(
            status_code=400,
            detail=f"Graph is paused at '{paused}', not 'idea_selection'."
        )

    result     = graph.invoke(Command(resume=data.selected_idea), config=config)
    generation = get_generation_by_workflow_thread(data.thread_id, db)

    return {
        "thread_id":     data.thread_id,
        "generation_id": generation.id if generation else None,
        "status":        "completed",
        "topic":         result.get("topic", ""),
        "research":      result.get("research", ""),
        "ideas":         result.get("ideas", []),
        "selected_idea": result.get("selected_idea", data.selected_idea),
        "script":        result.get("script", ""),
        "thumbnail":     result.get("thumbnail", ""),
        # No seo field here — use POST /workflow/upload/start when ready to publish
    }


@router.get("/status/{thread_id}")
def get_workflow_status(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    state  = graph.get_state(config)

    if not state or not state.values:
        raise HTTPException(status_code=404, detail="Thread not found.")

    return {
        "thread_id": thread_id,
        "is_paused": bool(state.next),
        "next_node": list(state.next) if state.next else [],
        "values":    state.values,
    }


# ── Generation history ────────────────────────────────────────────

@router.get("/history")
def get_generation_history(
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    generations = get_user_generations(
        user_id=current_user.id,
        db=db,
        limit=limit,
        offset=offset,
    )
    return {
        "total":   len(generations),
        "offset":  offset,
        "limit":   limit,
        "results": [
            {
                "id":            g.id,
                "topic":         g.topic,
                "plan":          g.plan,
                "status":        g.status,
                "selected_idea": g.selected_idea,
                "has_script":    bool(g.script),
                "has_thumbnail": bool(g.thumbnail),
                "created_at":    g.created_at,
            }
            for g in generations
        ],
    }


@router.get("/history/{generation_id}")
def get_generation_detail(
    generation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    generation = get_generation_by_id(generation_id, current_user.id, db)
    if not generation:
        raise HTTPException(status_code=404, detail="Generation not found.")

    return {
        "id":                       generation.id,
        "topic":                    generation.topic,
        "plan":                     generation.plan,
        "status":                   generation.status,
        "workflow_thread_id":       generation.workflow_thread_id,
        "research":                 generation.research,
        "ideas":                    generation.ideas,
        "selected_idea":            generation.selected_idea,
        "script":                   generation.script,
        "thumbnail":                generation.thumbnail,
        "creator_profile_snapshot": generation.creator_profile_snapshot,
        "error":                    generation.error,
        "created_at":               generation.created_at,
        "updated_at":               generation.updated_at,
    }


# ══════════════════════════════════════════════════════════════════
# UPLOAD / PUBLISHING WORKFLOW
# load_generation → seo_title → seo_description → tags →
# review_metadata (HITL) → upload_video → END
# ══════════════════════════════════════════════════════════════════

@router.post("/upload/start")
def start_upload_workflow(
    data: UploadStartRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Start the upload/publishing workflow for a completed generation.
    Generates SEO title, description, tags, then pauses for user review.
    """
    thread_id = str(uuid.uuid4())
    config    = {"configurable": {"thread_id": thread_id}}

    result = upload_graph.invoke(
        {
            "generation_id":  data.generation_id,
            "user_id":        current_user.id,
            "plan":           data.plan.value,
            "privacy_status": data.privacy_status,
        },
        config=config,
    )

    state  = upload_graph.get_state(config)
    paused = _paused_at(state)

    return {
        "thread_id":       thread_id,
        "status":          "awaiting_metadata_review" if paused else "completed",
        "paused_at":       paused,
        "seo_title":       result.get("seo_title", ""),
        "seo_description": result.get("seo_description", ""),
        "seo_tags":        result.get("seo_tags", []),
        "seo_hashtags":    result.get("seo_hashtags", []),
        "seo_category":    result.get("seo_category", ""),
        "privacy_status":  data.privacy_status,
    }


@router.post("/upload/review")
def review_upload_metadata(data: UploadReviewRequest):
    """
    HITL — User reviews and approves SEO metadata before upload.
    approved=true  → uploads to YouTube.
    approved=false → cancels upload.

    Optional fields (seo_title, seo_description, seo_tags, privacy_status)
    allow the user to override the generated values before approving.
    """
    config = {"configurable": {"thread_id": data.thread_id}}

    state = upload_graph.get_state(config)
    if not state or not state.values:
        raise HTTPException(
            status_code=404,
            detail=f"Upload thread '{data.thread_id}' not found."
        )
    if not state.next:
        raise HTTPException(status_code=400, detail="Upload workflow is not paused.")

    paused = _paused_at(state)
    if paused != "review_metadata":
        raise HTTPException(
            status_code=400,
            detail=f"Upload workflow paused at '{paused}', not 'review_metadata'."
        )

    # Apply any user overrides to state before resuming
    updates = {}
    if data.seo_title:       updates["seo_title"]       = data.seo_title
    if data.seo_description: updates["seo_description"] = data.seo_description
    if data.seo_tags:        updates["seo_tags"]        = data.seo_tags
    if data.privacy_status:  updates["privacy_status"]  = data.privacy_status

    if updates:
        upload_graph.update_state(config, updates)

    result = upload_graph.invoke(Command(resume=data.approved), config=config)

    if not data.approved:
        return {
            "thread_id": data.thread_id,
            "status":    "cancelled",
            "message":   "Upload cancelled by user.",
        }

    return {
        "thread_id":        data.thread_id,
        "status":           result.get("upload_status", "unknown"),
        "youtube_video_id": result.get("youtube_video_id", ""),
        "upload_error":     result.get("upload_error", ""),
        "seo_title":        result.get("seo_title", ""),
    }
