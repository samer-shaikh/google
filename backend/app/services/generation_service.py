"""
generation_service.py

All DB operations for generation history.
Called from workflow route nodes — never opens its own session.
"""
from sqlalchemy.orm import Session
from app.models.generation import Generation


def create_generation(
    user_id: int,
    topic: str,
    workflow_thread_id: str,
    plan: str,
    db: Session,
) -> Generation:
    """Create a pending generation record at workflow start."""
    gen = Generation(
        user_id=user_id,
        topic=topic,
        workflow_thread_id=workflow_thread_id,
        plan=plan,
        status="pending",
    )
    db.add(gen)
    db.commit()
    db.refresh(gen)
    return gen


def save_research(
    generation_id: int,
    research: str,
    db: Session,
) -> None:
    """Save research output after research node completes."""
    db.query(Generation).filter(
        Generation.id == generation_id
    ).update({"research": research})
    db.commit()


def complete_generation(
    generation_id: int,
    ideas: list,
    selected_idea: str,
    script: str,
    thumbnail: str,
    seo: str,
    creator_profile_snapshot: dict,
    db: Session,
) -> Generation:
    """Mark generation complete and save all outputs."""
    db.query(Generation).filter(
        Generation.id == generation_id
    ).update({
        "status":                   "completed",
        "ideas":                    ideas,
        "selected_idea":            selected_idea,
        "script":                   script,
        "thumbnail":                thumbnail,
        "seo":                      seo,
        "creator_profile_snapshot": creator_profile_snapshot,
    })
    db.commit()

    return db.query(Generation).filter(
        Generation.id == generation_id
    ).first()


def fail_generation(
    generation_id: int,
    error: str,
    db: Session,
) -> None:
    """Mark generation failed with error message."""
    db.query(Generation).filter(
        Generation.id == generation_id
    ).update({"status": "failed", "error": error})
    db.commit()


def get_user_generations(
    user_id: int,
    db: Session,
    limit: int = 20,
    offset: int = 0,
) -> list[Generation]:
    return (
        db.query(Generation)
        .filter(Generation.user_id == user_id)
        .order_by(Generation.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def get_generation_by_id(
    generation_id: int,
    user_id: int,
    db: Session,
) -> Generation | None:
    return (
        db.query(Generation)
        .filter(
            Generation.id == generation_id,
            Generation.user_id == user_id,
        )
        .first()
    )


def get_generation_by_workflow_thread(
    workflow_thread_id: str,
    db: Session,
) -> Generation | None:
    return (
        db.query(Generation)
        .filter(Generation.workflow_thread_id == workflow_thread_id)
        .first()
    )
