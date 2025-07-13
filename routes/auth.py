from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from typing import Optional
from database import SessionLocal
from models import User

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class RegisterRequest(BaseModel):
    name: str
    company: Optional[str] = None
    phone: str
    email: EmailStr
    password: str

@router.post("/register/")
def register_user(data: RegisterRequest, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.phone == data.phone).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Пользователь с таким номером уже существует")

    hashed_password = pwd_context.hash(data.password)

    user = User(
        name=data.name,
        company=data.company,
        phone=data.phone,
        email=data.email,
        password_hash=hashed_password
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {"message": "Пользователь успешно зарегистрирован", "user_id": user.id}
