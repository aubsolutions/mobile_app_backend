# routes/auth.py

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any
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

# tokenUrl нужен для Swagger; сам токен подходит и владельцу, и сотруднику
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")


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
    name: Optional[str] = None
    company: Optional[str] = None
    email: Optional[EmailStr] = None


class LoginRequest(BaseModel):
    phone: str
    password: str


# ---------------------
# Регистрация пользователя (владелец)
# ---------------------
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

    # Бесплатная подписка на 14 дней
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


# ---------------------
# Единый логин (владелец ИЛИ сотрудник)
# ---------------------
@router.post("/login")
def login_any(data: LoginRequest, db: Session = Depends(get_db)):
    """
    Пытаемся:
      1) Владелец (User)
      2) Сотрудник (Employee)
    Возвращаем access_token с sub:
      - user: "<user_id>"
      - employee: "emp:<employee_id>"
    """
    # 1) Владелец
    user = db.query(User).filter(User.phone == data.phone).first()
    if user and pwd_context.verify(data.password, user.password_hash):
        token_data = {
            "sub": str(user.id),
            "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        }
        token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
        return {"access_token": token, "token_type": "bearer"}

    # 2) Сотрудник
    emp = db.query(Employee).filter(Employee.phone == data.phone).first()
    if emp and pwd_context.verify(data.password, emp.password_hash):
        if emp.is_blocked:
            # Отдельное сообщение, чтобы было понятно пользователю
            raise HTTPException(status_code=403, detail="Ваша учетная запись заблокирована")
        token_data = {
            "sub": f"emp:{emp.id}",
            "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        }
        token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
        return {"access_token": token, "token_type": "bearer"}

    # 3) Никто не подошёл
    raise HTTPException(status_code=401, detail="Неверный номер телефона или пароль")


# ---------------------
# (Опционально) Старый логин для сотрудника — оставлен для совместимости
# ---------------------
@router.post("/employee/login")
def login_employee_legacy(data: LoginRequest, db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.phone == data.phone).first()
    if not emp or not pwd_context.verify(data.password, emp.password_hash):
        raise HTTPException(status_code=401, detail="Неверный номер телефона или пароль")
    if emp.is_blocked:
        raise HTTPException(status_code=403, detail="Ваша учетная запись заблокирована")

    token_data = {
        "sub": f"emp:{emp.id}",
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    token = jwt.encode(token_data, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}


# ---------------------
# Зависимости (guard'ы)
# ---------------------
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    # Ожидаем токен владельца: sub == "<user_id>"
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if sub is None or not str(sub).isdigit():
            # Токен валиден, но роль не владелец
            raise HTTPException(status_code=403, detail="Доступ запрещён: требуется вход как владелец")
        user_id = int(sub)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Сессия истекла или недействительна. Войдите снова")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user


def get_current_employee(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Employee:
    # Ожидаем токен сотрудника: sub == "emp:<id>"
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub", "")
        if not isinstance(sub, str) or not sub.startswith("emp:"):
            raise HTTPException(status_code=403, detail="Доступ запрещён: требуется вход как сотрудник")
        emp_id = int(sub.split(":", 1)[1])
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Сессия истекла или недействительна. Войдите снова")

    emp = db.query(Employee).filter(Employee.id == emp_id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    if emp.is_blocked:
        raise HTTPException(status_code=403, detail="Учетная запись заблокирована")
    return emp


# Универсальный резолвер актёра (владелец или сотрудник)
def get_actor(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Возвращает:
      {"role": "user", "user": <User>, "employee": None}
      или
      {"role": "employee", "user": None, "employee": <Employee>}
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

    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Сессия истекла или недействительна. Войдите снова")


# ---------------------
# Профиль: универсально для владельца и сотрудника
# ---------------------
@router.get("/me")
def get_me(
    actor: Dict[str, Any] = Depends(get_actor),
    db: Session = Depends(get_db),
):
    if actor["role"] == "user":
        user: User = actor["user"]
        sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
        return {
            "role": "user",
            "id": user.id,
            "name": user.name,
            "company": user.company,
            "phone": user.phone,
            "email": user.email,
            "terms_accepted_at": user.terms_accepted_at,
            "subscription_end": sub.end_date if sub else None,
        }
    else:
        emp: Employee = actor["employee"]
        owner = db.query(User).filter(User.id == emp.owner_id).first()
        return {
            "role": "employee",
            "id": emp.id,
            "name": emp.name,
            "phone": emp.phone,
            "owner_id": emp.owner_id,
            "owner_name": owner.name if owner else None,
            "owner_company": owner.company if owner else None,
            "is_blocked": emp.is_blocked,
        }


# ---------------------
# Обновление профиля владельца
# ---------------------
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