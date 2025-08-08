# routes/auth.py

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timedelta

from jose import jwt

from database import get_db
from models import User, Subscription, Employee

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 🔐 JWT настройки
SECRET_KEY = "super-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 день

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


# ---------------------
# Утилита нормализации телефона
# Приводим к 11-значному формату под РК: 7XXXXXXXXXX (только цифры)
# ---------------------
def normalize_phone(phone: str) -> str:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(digits) == 11 and digits.startswith("8"):
        # 8XXXXXXXXXX -> 7XXXXXXXXXX
        digits = "7" + digits[1:]
    if len(digits) == 10:
        # XXXXXXXXXX -> 7XXXXXXXXXX
        digits = "7" + digits
    return digits


# ---------------------
# Pydantic модели
# ---------------------
class RegisterRequest(BaseModel):
    name: str
    company: Optional[str] = None
    phone: str
    email: EmailStr
    password: str
    terms_accepted_at: datetime

class UpdateUserRequest(BaseModel):
    name: Optional[str]
    company: Optional[str]
    email: Optional[EmailStr]

class LoginRequest(BaseModel):
    phone: str
    password: str

class EmployeeLoginRequest(BaseModel):
    phone: str
    password: str


# ---------------------
# Регистрация пользователя
# ---------------------
@router.post("/register/")
def register_user(data: RegisterRequest, db: Session = Depends(get_db)):
    norm_phone = normalize_phone(data.phone)

    # проверим коллизии по нормализованному телефону
    existing = None
    for u in db.query(User).all():
        if normalize_phone(u.phone) == norm_phone:
            existing = u
            break
    if existing:
        raise HTTPException(status_code=400, detail="Пользователь с таким номером уже существует")

    hashed = pwd_context.hash(data.password)
    user = User(
        name=data.name,
        company=data.company,
        phone=norm_phone,  # сохраняем уже нормализованный
        email=data.email,
        password_hash=hashed,
        terms_accepted_at=data.terms_accepted_at
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # бесплатная подписка на 14 дней
    sub = Subscription(
        user_id=user.id,
        type="free",
        start_date=datetime.utcnow(),
        end_date=datetime.utcnow() + timedelta(days=14)
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)

    return {
        "message": "Пользователь успешно зарегистрирован",
        "user_id": user.id,
        "subscription_end": sub.end_date
    }


# ---------------------
# Единый логин: сначала владелец, потом сотрудник (с нормализацией телефона)
# ---------------------
@router.post("/login")
def login_user(data: LoginRequest, db: Session = Depends(get_db)):
    norm_phone = normalize_phone(data.phone)

    # 1) Пытаемся как ВЛАДЕЛЕЦ — ищем по нормализованному совпадению
    user = None
    for u in db.query(User).all():
        if normalize_phone(u.phone) == norm_phone:
            user = u
            break
    if user and pwd_context.verify(data.password, user.password_hash):
        token_data = {
            "sub": str(user.id),
            "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        }
        token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
        return {"access_token": token, "token_type": "bearer"}

    # 2) Пытаемся как СОТРУДНИК — также по нормализованному совпадению
    emp = None
    for e in db.query(Employee).all():
        if normalize_phone(e.phone) == norm_phone:
            emp = e
            break
    if emp and pwd_context.verify(data.password, emp.password_hash):
        if emp.is_blocked:
            raise HTTPException(status_code=403, detail="Ваша учетная запись заблокирована")
        token_data = {
            "sub": f"emp:{emp.id}",
            "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        }
        token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
        return {"access_token": token, "token_type": "bearer"}

    # 3) Не подошёл ни владелец, ни сотрудник
    raise HTTPException(status_code=401, detail="Неверный номер или пароль")


# ---------------------
# Логин сотрудника (опционально оставляем)
# ---------------------
@router.post("/employee/login")
def login_employee(data: EmployeeLoginRequest, db: Session = Depends(get_db)):
    norm_phone = normalize_phone(data.phone)
    emp = None
    for e in db.query(Employee).all():
        if normalize_phone(e.phone) == norm_phone:
            emp = e
            break

    if not emp or not pwd_context.verify(data.password, emp.password_hash):
        raise HTTPException(status_code=401, detail="Неверный номер или пароль")
    if emp.is_blocked:
        raise HTTPException(status_code=403, detail="Ваша учетная запись заблокирована")

    token_data = {
        "sub": f"emp:{emp.id}",
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    }
    token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}


# ---------------------
# Зависимость: текущий пользователь
# ---------------------
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None or not str(sub).isdigit():
            raise ValueError()
        user_id = int(sub)
    except Exception:
        raise HTTPException(status_code=401, detail="Невалидный токен пользователя")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user


# ---------------------
# Зависимость: текущий сотрудник
# ---------------------
def get_current_employee(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Employee:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub", "")
        if not isinstance(sub, str) or not sub.startswith("emp:"):
            raise ValueError()
        emp_id = int(sub.split(":", 1)[1])
    except Exception:
        raise HTTPException(status_code=401, detail="Невалидный токен сотрудника")

    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    if emp.is_blocked:
        raise HTTPException(status_code=403, detail="Учетная запись заблокирована")
    return emp


# --- Универсальный резолвер актёра по токену (владелец или сотрудник) ---
def get_actor(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    """
    Возвращает словарь:
      - {"role": "user", "user": <User>, "employee": None}
      - {"role": "employee", "user": None, "employee": <Employee>}
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub", "")

        # Сотрудник
        if isinstance(sub, str) and sub.startswith("emp:"):
            emp_id = int(sub.split(":", 1)[1])
            emp = db.query(Employee).filter(Employee.id == emp_id).first()
            if not emp:
                raise HTTPException(status_code=404, detail="Сотрудник не найден")
            if emp.is_blocked:
                raise HTTPException(status_code=403, detail="Учетная запись заблокирована")
            return {"role": "employee", "employee": emp, "user": None}

        # Владелец
        user_id = int(sub)
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        return {"role": "user", "employee": None, "user": user}

    except Exception:
        raise HTTPException(status_code=401, detail="Невалидный токен")


# ---------------------
# Профиль текущего пользователя (для фронта /me)
# ---------------------
@router.get("/me")
def get_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    sub = db.query(Subscription).filter(Subscription.user_id == current_user.id).first()
    return {
        "id": current_user.id,
        "name": current_user.name,
        "company": current_user.company,
        "phone": current_user.phone,
        "email": current_user.email,
        "terms_accepted_at": current_user.terms_accepted_at,
        "subscription_end": sub.end_date if sub else None
    }


# ---------------------
# Обновление профиля (если нужно на экране редактирования)
# ---------------------
@router.put("/me")
def update_me(
    data: UpdateUserRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
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