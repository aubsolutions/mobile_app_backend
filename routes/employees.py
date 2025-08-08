# routes/employees.py

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from passlib.context import CryptContext
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

from database import get_db
from models import Employee, User, Invoice, Item
from routes.auth import get_current_user  # только владелец

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
router = APIRouter(prefix="/employees", tags=["employees"])

# Pydantic-схемы
class EmployeeCreate(BaseModel):
    name: str
    phone: str
    password: str

class EmployeeOut(BaseModel):
    id: int
    name: str
    phone: str
    is_blocked: bool
    class Config:
        orm_mode = True

class EmployeeUpdatePhone(BaseModel):
    phone: str

class EmployeeUpdatePassword(BaseModel):
    password: str

# GET /employees — список сотрудников владельца
@router.get("/", response_model=List[EmployeeOut])
def list_employees(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Employee).filter(Employee.owner_id == current_user.id).all()

# POST /employees — создать сотрудника
@router.post("/", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
def create_employee(
    data: EmployeeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if db.query(Employee).filter(Employee.phone == data.phone).first():
        raise HTTPException(status_code=400, detail="Сотрудник с таким телефоном уже существует")
    emp = Employee(
        owner_id=current_user.id,
        name=data.name,
        phone=data.phone,
        password_hash=pwd_context.hash(data.password),
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return emp

# PUT /employees/{emp_id}/phone — смена телефона
@router.put("/{emp_id}/phone", response_model=EmployeeOut)
def update_phone(
    emp_id: int,
    data: EmployeeUpdatePhone,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    emp = db.query(Employee).filter_by(id=emp_id, owner_id=current_user.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    emp.phone = data.phone
    db.commit()
    db.refresh(emp)
    return emp

# PUT /employees/{emp_id}/password — смена пароля
@router.put("/{emp_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def update_password(
    emp_id: int,
    data: EmployeeUpdatePassword,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    emp = db.query(Employee).filter_by(id=emp_id, owner_id=current_user.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    emp.password_hash = pwd_context.hash(data.password)
    db.commit()

# POST /employees/{emp_id}/block — блокировка
@router.post("/{emp_id}/block", status_code=status.HTTP_204_NO_CONTENT)
def block_employee(
    emp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    emp = db.query(Employee).filter_by(id=emp_id, owner_id=current_user.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    emp.is_blocked = True
    db.commit()

# POST /employees/{emp_id}/unblock — разблокировка
@router.post("/{emp_id}/unblock", status_code=status.HTTP_204_NO_CONTENT)
def unblock_employee(
    emp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    emp = db.query(Employee).filter_by(id=emp_id, owner_id=current_user.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    emp.is_blocked = False
    db.commit()

# DELETE /employees/{emp_id} — удалить
@router.delete("/{emp_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_employee(
    emp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    emp = db.query(Employee).filter_by(id=emp_id, owner_id=current_user.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    db.delete(emp)
    db.commit()

# -------------------------
# GET /employees/stats — агрегаты по продавцам
# -------------------------
@router.get("/stats")
def employees_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    """
    Агрегированные продажи по каждому продавцу (включая владельца, если seller_employee_id = NULL):
      - total_sum: сумма (quantity*price)
      - total_invoices: кол-во чеков
      - total_paid: оплачено
      - total_debt: долг = max(sum - paid, 0)
    """
    gross_sum = func.coalesce(func.sum(Item.quantity * Item.price), 0).label("total_sum")
    invoice_count = func.count(func.distinct(Invoice.id)).label("total_invoices")
    paid_sum = func.coalesce(func.sum(Invoice.paid_amount), 0).label("total_paid")

    q = (
        db.query(
            Invoice.seller_employee_id,
            Invoice.seller_name,
            gross_sum,
            invoice_count,
            paid_sum,
        )
        .outerjoin(Item, Item.invoice_id == Invoice.id)
        .filter(Invoice.user_id == current_user.id)
    )

    # Фильтры по дате, если заданы
    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            q = q.filter(Invoice.created_at >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            q = q.filter(Invoice.created_at <= dt_to.replace(hour=23, minute=59, second=59, microsecond=999999))
        except ValueError:
            pass

    q = q.group_by(Invoice.seller_employee_id, Invoice.seller_name)

    rows = q.all()
    out = []
    for row in rows:
        total_sum = int(row.total_sum or 0)
        total_paid = int(row.total_paid or 0)
        out.append({
            "seller_employee_id": row.seller_employee_id,   # None => оформлял владелец
            "seller_name": row.seller_name,
            "total_sum": total_sum,
            "total_invoices": int(row.total_invoices or 0),
            "total_paid": total_paid,
            "total_debt": max(total_sum - total_paid, 0),
        })
    return out