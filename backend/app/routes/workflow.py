import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from langgraph.types import Command

from app.graph.workflow import graph
from app.graph.upload_workflow import upload_graph
from app.models.plan import Plan

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


# ── helpers ───────────────────────────────────────────────────────

def _paused_at(state) -> str:
    """Return the name of the node the graph is currently interrupted at."""
    if state and state.next:
        return list(state.next)[0]
    return ""


# ── Main pipeline ─────────────────────────────────────────────────

@router.post("/run")
def run_workflow(data: WorkflowStartRequest):
    """
    Starts the pipeline.
    Runs Research then pauses at human_approval (HITL #1).
    Returns thread_id + research for the user to review.
    """
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    result = graph.invoke(
        {"topic": data.topic, "plan": data.plan.value},
        config=config,
    )

    state = graph.get_state(config)
    paused = _paused_at(state)

    return {
        "thread_id": thread_id,
        "status": "awaiting_approval" if paused else "completed",
        "paused_at": paused,
        "research": result.get("research", ""),
    }


@router.post("/resume")
def resume_workflow(data: WorkflowResumeRequest):
    """
    HITL #1 — Research approval.
    Command(resume=True)  → continues to Ideas node then pauses at idea_selection.
    Command(resume=False) → ends the workflow.
    """
    config = {"configurable": {"thread_id": data.thread_id}}

    state = graph.get_state(config)
    if not state or not state.values:
        raise HTTPException(
            status_code=404,
            detail=f"Thread '{data.thread_id}' not found. "
                   "If the server was restarted, in-memory state is lost — start a new run."
        )
    if not state.next:
        raise HTTPException(status_code=400, detail="Workflow is not paused.")

    paused = _paused_at(state)
    if paused != "human_approval":
        raise HTTPException(
            status_code=400,
            detail=f"Graph is paused at '{paused}', not 'human_approval'. "
                   "Use /select-idea to resume from idea_selection."
        )

    result = graph.invoke(Command(resume=data.approved), config=config)

    if not data.approved:
        return {
            "thread_id": data.thread_id,
            "status": "rejected",
            "message": "Workflow rejected. No further agents ran.",
        }

    # After approving, the graph runs Ideas then pauses at idea_selection
    new_state = graph.get_state(config)
    paused_now = _paused_at(new_state)

    ideas_raw = result.get("ideas", [])
    ideas = ideas_raw if isinstance(ideas_raw, list) else []

    return {
        "thread_id": data.thread_id,
        "status": "awaiting_idea_selection" if paused_now == "idea_selection" else "completed",
        "paused_at": paused_now,
        "ideas": ideas,
        # also pass research back so frontend still has it
        "research": result.get("research", ""),
    }


@router.post("/select-idea")
def select_idea(data: IdeaSelectRequest):
    """
    HITL #2 — Idea selection.
    Resumes from idea_selection with the chosen idea string.
    Runs Script → Thumbnail → SEO → END and returns all outputs.
    """
    config = {"configurable": {"thread_id": data.thread_id}}

    state = graph.get_state(config)
    if not state or not state.values:
        raise HTTPException(
            status_code=404,
            detail=f"Thread '{data.thread_id}' not found."
        )
    if not state.next:
        raise HTTPException(status_code=400, detail="Workflow is not paused.")

    paused = _paused_at(state)
    if paused != "idea_selection":
        raise HTTPException(
            status_code=400,
            detail=f"Graph is paused at '{paused}', not 'idea_selection'."
        )

    # Resume with the selected idea string — this is what interrupt() returns
    result = graph.invoke(Command(resume=data.selected_idea), config=config)

    return {
        "thread_id": data.thread_id,
        "status": "completed",
        "topic":        result.get("topic", ""),
        "research":     result.get("research", ""),
        "ideas":        result.get("ideas", []),
        "selected_idea":result.get("selected_idea", data.selected_idea),
        "script":       result.get("script", ""),
        "thumbnail":    result.get("thumbnail", ""),
        "seo":          result.get("seo", ""),
    }


@router.get("/status/{thread_id}")
def get_workflow_status(thread_id: str):
    """Poll the current state of any workflow run."""
    config = {"configurable": {"thread_id": thread_id}}
    state = graph.get_state(config)

    if not state or not state.values:
        raise HTTPException(status_code=404, detail="Thread not found.")

    return {
        "thread_id": thread_id,
        "is_paused": bool(state.next),
        "next_node": list(state.next) if state.next else [],
        "values":    state.values,
    }


# ── Upload optimizer (separate post-production workflow) ──────────

@router.post("/optimize-upload")
def optimize_upload(data: UploadOptimizeRequest):
    """
    Standalone post-production workflow — call after main pipeline completes.
    No HITL, no thread tracking, single-shot.
    """
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
