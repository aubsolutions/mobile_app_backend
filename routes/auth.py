# routes/auth.py

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy import or_
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from jose import jwt
import re

from database import get_db
from models import User, Subscription, Employee

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 🔐 JWT
SECRET_KEY = "super-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 день

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


# ───────────────────────────────────────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНОЕ: нормализация телефонов
# ───────────────────────────────────────────────────────────────────────────────
def norm_phone(s: Optional[str]) -> str:
    """Оставляем только цифры."""
    return re.sub(r"\D+", "", s or "")

def eq_phone(a: str, b: str) -> bool:
    """Сравниваем по последним 10 цифрам (без кода страны)."""
    na = norm_phone(a)[-10:]
    nb = norm_phone(b)[-10:]
    return bool(na) and na == nb


# ───────────────────────────────────────────────────────────────────────────────
# Pydantic модели
# ───────────────────────────────────────────────────────────────────────────────
class RegisterRequest(BaseModel):
    name: str
    company: Optional[str] = None
    phone: str
    email: EmailStr
    password: str
    terms_accepted_at: datetime

class UpdateUserRequest(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    email: Optional[EmailStr] = None

class LoginRequest(BaseModel):
    phone: str
    password: str

class EmployeeLoginRequest(BaseModel):
    phone: str
    password: str


# ───────────────────────────────────────────────────────────────────────────────
# Регистрация владельца
# ───────────────────────────────────────────────────────────────────────────────
@router.post("/register/")
def register_user(data: RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.phone == data.phone).first()
    if existing:
        raise HTTPException(status_code=400, detail="Пользователь с таким номером уже существует")

    hashed = pwd_context.hash(data.password)
    user = User(
        name=data.name,
        company=data.company,
        phone=data.phone,
        email=data.email,
        password_hash=hashed,
        terms_accepted_at=data.terms_accepted_at,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # бесплатная подписка на 14 дней
    sub = Subscription(
        user_id=user.id,
        type="free",
        start_date=datetime.utcnow(),
        end_date=datetime.utcnow() + timedelta(days=14),
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)

    return {
        "message": "Пользователь успешно зарегистрирован",
        "user_id": user.id,
        "subscription_end": sub.end_date,
    }


# ───────────────────────────────────────────────────────────────────────────────
# ЕДИНЫЙ ЛОГИН: принимает владельца ИЛИ сотрудника
# ───────────────────────────────────────────────────────────────────────────────
@router.post("/login")
def login_any(data: LoginRequest, db: Session = Depends(get_db)):
    raw_phone = data.phone or ""
    # допускаем, что при создании пароля могли случайно оставить пробелы
    pwd_candidates = [data.password, data.password.strip()]

    # 1) Прямая попытка: владелец по точному номеру
    user = db.query(User).filter(User.phone == raw_phone).first()
    if user:
        for p in pwd_candidates:
            if pwd_context.verify(p, user.password_hash):
                token_data = {
                    "sub": str(user.id),
                    "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
                }
                token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
                return {"access_token": token, "token_type": "bearer"}

    # 2) Прямая попытка: сотрудник по точному номеру
    emp = db.query(Employee).filter(Employee.phone == raw_phone).first()
    if emp:
        for p in pwd_candidates:
            if pwd_context.verify(p, emp.password_hash):
                if emp.is_blocked:
                    raise HTTPException(status_code=403, detail="Ваша учетная запись заблокирована")
                token_data = {
                    "sub": f"emp:{emp.id}",
                    "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
                }
                token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
                return {"access_token": token, "token_type": "bearer"}

    # 3) Толерантный поиск по последним 10 цифрам (если форматы различаются)
    last10 = norm_phone(raw_phone)[-10:]
    if last10:
        # кандидаты-владельцы
        cand_users = db.query(User).filter(
            or_(User.phone.contains(last10), User.phone == raw_phone)
        ).all()
        for u in cand_users:
            if eq_phone(u.phone, raw_phone):
                for p in pwd_candidates:
                    if pwd_context.verify(p, u.password_hash):
                        token_data = {
                            "sub": str(u.id),
                            "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
                        }
                        token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
                        return {"access_token": token, "token_type": "bearer"}

        # кандидаты-сотрудники
        cand_emps = db.query(Employee).filter(
            or_(Employee.phone.contains(last10), Employee.phone == raw_phone)
        ).all()
        for e in cand_emps:
            if eq_phone(e.phone, raw_phone):
                for p in pwd_candidates:
                    if pwd_context.verify(p, e.password_hash):
                        if e.is_blocked:
                            raise HTTPException(status_code=403, detail="Ваша учетная запись заблокирована")
                        token_data = {
                            "sub": f"emp:{e.id}",
                            "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
                        }
                        token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
                        return {"access_token": token, "token_type": "bearer"}

    # если ничего не подошло
    raise HTTPException(status_code=401, detail="Неверный номер телефона или пароль")


# (оставляем для Swagger совместимости — работает так же, как /login)
@router.post("/employee/login")
def login_employee(data: EmployeeLoginRequest, db: Session = Depends(get_db)):
    return login_any(LoginRequest(phone=data.phone, password=data.password), db)  # type: ignore


# ───────────────────────────────────────────────────────────────────────────────
# Зависимости
# ───────────────────────────────────────────────────────────────────────────────
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None or not str(sub).isdigit():
            raise ValueError("not owner token")
        user_id = int(sub)
    except Exception:
        raise HTTPException(status_code=401, detail="Невалидный токен пользователя")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user


def get_current_employee(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Employee:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub", "")
        if not isinstance(sub, str) or not sub.startswith("emp:"):
            raise ValueError("not employee token")
        emp_id = int(sub.split(":", 1)[1])
    except Exception:
        raise HTTPException(status_code=401, detail="Невалидный токен сотрудника")

    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    if emp.is_blocked:
        raise HTTPException(status_code=403, detail="Учетная запись заблокирована")
    return emp


def get_actor(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Универсальный резолвер: владелец или сотрудник по токену."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub", "")

        if isinstance(sub, str) and sub.startswith("emp:"):
            emp_id = int(sub.split(":", 1)[1])
            emp = db.query(Employee).filter(Employee.id == emp_id).first()
            if not emp:
                raise HTTPException(status_code=404, detail="Сотрудник не найден")
            if emp.is_blocked:
                raise HTTPException(status_code=403, detail="Учетная запись заблокирована")
            return {"role": "employee", "employee": emp, "user": None}

        user_id = int(sub)
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        return {"role": "user", "employee": None, "user": user}

    except Exception:
        raise HTTPException(status_code=401, detail="Невалидный токен")


# ───────────────────────────────────────────────────────────────────────────────
# Профиль
# ───────────────────────────────────────────────────────────────────────────────
@router.get("/me")
def get_me(
    actor: Dict[str, Any] = Depends(get_actor),
    db: Session = Depends(get_db),
):
    if actor["role"] == "user":
        u: User = actor["user"]
        sub = db.query(Subscription).filter(Subscription.user_id == u.id).first()
        return {
            "role": "user",
            "id": u.id,
            "name": u.name,
            "company": u.company,
            "phone": u.phone,
            "email": u.email,
            "terms_accepted_at": u.terms_accepted_at,
            "subscription_end": sub.end_date if sub else None,
        }
    else:
        e: Employee = actor["employee"]
        owner = db.query(User).filter(User.id == e.owner_id).first()
        return {
            "role": "employee",
            "id": e.id,
            "name": e.name,
            "phone": e.phone,
            "owner_id": e.owner_id,
            "is_blocked": e.is_blocked,
            # чтобы в профиле показывалось название организации
            "company": owner.company if owner else None,
            "owner_name": owner.name if owner else None,
            "owner_company": owner.company if owner else None,
        }


# ───────────────────────────────────────────────────────────────────────────────
# Обновление профиля владельца
# ───────────────────────────────────────────────────────────────────────────────
@router.put("/me")
def update_me(
    data: UpdateUserRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.name is not None:
        current_user.name = data.name
    if data.company is not None:
        current_user.company = data.company
    if data.email is not None:
        current_user.email = data.email

    db.commit()
    db.refresh(current_user)
    return {"message": "Профиль обновлён"}