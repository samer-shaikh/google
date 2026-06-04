from pydantic import BaseModel

class ThreadCreate(BaseModel):
    title: str

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.thread import Thread
from app.models.user import User
from app.dependencies.auth import get_current_user

from app.models.generation import Generation
from app.schemas.generation import GenerationRequest


router = APIRouter(
    prefix="/threads",
    tags=["Threads"]
)

@router.post("/")
def create_thread(
    data: ThreadCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    thread = Thread(
        title=data.title,
        user_id=current_user.id
    )

    db.add(thread)
    db.commit()
    db.refresh(thread)

    return thread

@router.get("/")
def get_threads(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return (
        db.query(Thread)
        .filter(Thread.user_id == current_user.id)
        .all()
    )

@router.post("/{thread_id}/generate")
def generate(
    thread_id: int,
    data: GenerationRequest,
    db: Session = Depends(get_db)
):
    
    result = "This is a test AI response"

    generation = Generation(
                    thread_id=thread_id,
                    prompt=data.prompt,
                    result=result,
                    status="completed"
                )
    
    db.add(generation)
    db.commit()
    db.refresh(generation)

    return {
        'thread_id':thread_id,
        'prompt':data.prompt,
        'result':result,
        'status':"completed"
    }