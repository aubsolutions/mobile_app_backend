from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Feedback, User
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from routes.auth import get_current_user

router = APIRouter()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class FeedbackCreate(BaseModel):
    message: str
    name: Optional[str] = None

@router.post("/feedback/")
def submit_feedback(
    feedback: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),  # можно заменить на Optional
):
    if not feedback.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    fb = Feedback(
        user_id=current_user.id if current_user else None,
        message=feedback.message.strip(),
        name=feedback.name,
        created_at=datetime.utcnow(),
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return {"message": "Спасибо за ваш отзыв!"}
