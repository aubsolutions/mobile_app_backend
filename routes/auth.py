from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from typing import Optional
from jose import JWTError, jwt
from datetime import datetime, timedelta
from fastapi.security import OAuth2PasswordBearer
from database import SessionLocal
from models import User

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 🔐 JWT настройки
SECRET_KEY = "super-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 день

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

# ---------------------
# DB dependency
# ---------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------------
# Pydantic модели
# ---------------------
class RegisterRequest(BaseModel):
    name: str
    company: Optional[str] = None
    phone: str
    email: EmailStr
    password: str

class UpdateUserRequest(BaseModel):
    name: Optional[str]
    company: Optional[str]
    email: Optional[EmailStr]

class LoginRequest(BaseModel):
    phone: str
    password: str

# ---------------------
# Регистрация
# ---------------------
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

# ---------------------
# Логин
# ---------------------
@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.phone == data.phone).first()
    if not user or not pwd_context.verify(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверный номер или пароль")

    token_data = {
        "sub": str(user.id),
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    }
    token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}

# ---------------------
# Получение текущего пользователя
# ---------------------
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError):
        raise HTTPException(status_code=401, detail="Невалидный токен")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    return user

# ---------------------
# Получение профиля
# ---------------------
@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "name": current_user.name,
        "company": current_user.company,
        "phone": current_user.phone,
        "email": current_user.email,
    }

# ---------------------
# Обновление профиля
# ---------------------
@router.put("/me")
def update_user_profile(
    update_data: UpdateUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if update_data.name is not None:
        current_user.name = update_data.name
    if update_data.company is not None:
        current_user.company = update_data.company
    if update_data.email is not None:
        current_user.email = update_data.email

    db.commit()
    db.refresh(current_user)
    return {"message": "Профиль обновлён"}
