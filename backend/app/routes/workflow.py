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

class UploadOptimizeRequest(BaseModel):
    topic: str
    script: str
    seo: str = ""
    plan: Plan = Plan.normal


# ── Helper ────────────────────────────────────────────────────────

def _paused_at(state) -> str:
    if state and state.next:
        return list(state.next)[0]
    return ""


# ── Main pipeline ─────────────────────────────────────────────────

@router.post("/run")
def run_workflow(
    data: WorkflowStartRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Starts the full pipeline.
    1. Creates a 'pending' generation record in DB
    2. Loads creator profile
    3. Runs Research
    4. Pauses at human_approval (HITL #1)
    Returns thread_id + generation_id + research output.
    """
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    # Create generation record immediately so we have an ID to track
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
    True  → continues to Ideas then pauses at idea_selection.
    False → marks generation as rejected and ends.
    """
    config = {"configurable": {"thread_id": data.thread_id}}

    state = graph.get_state(config)
    if not state or not state.values:
        raise HTTPException(
            status_code=404,
            detail=f"Thread '{data.thread_id}' not found. "
                   "Server may have restarted — start a new run."
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
    ideas_raw  = result.get("ideas", [])
    ideas      = ideas_raw if isinstance(ideas_raw, list) else []

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
    Resumes pipeline, runs Script → Thumbnail → SEO → save_generation → END.
    Returns the complete generation output.
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

    result = graph.invoke(Command(resume=data.selected_idea), config=config)

    # Fetch the saved generation from DB to confirm it was saved
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
        "seo":           result.get("seo", ""),
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
    """
    Returns all past generations for the current user,
    newest first. Each item includes all outputs.
    """
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
                "has_seo":       bool(g.seo),
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
    """
    Returns the full output of a single generation.
    Use this when the user clicks on a history item in the frontend.
    """
    generation = get_generation_by_id(generation_id, current_user.id, db)

    if not generation:
        raise HTTPException(
            status_code=404,
            detail="Generation not found."
        )

    return {
        "id":                       generation.id,
        "topic":                    generation.topic,
        "plan":                     generation.plan,
        "status":                   generation.status,
        "workflow_thread_id":        generation.workflow_thread_id,
        "research":                 generation.research,
        "ideas":                    generation.ideas,
        "selected_idea":            generation.selected_idea,
        "script":                   generation.script,
        "thumbnail":                generation.thumbnail,
        "seo":                      generation.seo,
        "creator_profile_snapshot": generation.creator_profile_snapshot,
        "error":                    generation.error,
        "created_at":               generation.created_at,
        "updated_at":               generation.updated_at,
    }


# ── Upload optimizer ──────────────────────────────────────────────

@router.post("/optimize-upload")
def optimize_upload(data: UploadOptimizeRequest):
    result = upload_graph.invoke({
        "topic":  data.topic,
        "script": data.script,
        "seo":    data.seo,
        "plan":   data.plan.value,
    })
    return {
        "status": "completed",
        "upload": result.get("upload", ""),
    }
