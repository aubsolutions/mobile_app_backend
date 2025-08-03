# routes/employees.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from pydantic import BaseModel
from typing import List

from database import get_db
from models import Employee, User
from auth import get_current_user, get_current_employee

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

# GET /employees
@router.get("/", response_model=List[EmployeeOut])
def list_employees(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_employee),
):
    return db.query(Employee).filter(Employee.owner_id == current_user.id).all()

# POST /employees
@router.post("/", response_model=EmployeeOut, status_code=status.HTTP_201_CREATED)
def create_employee(
    data: EmployeeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_employee),
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

# PUT /employees/{emp_id}/phone
@router.put("/{emp_id}/phone", response_model=EmployeeOut)
def update_phone(
    emp_id: int,
    data: EmployeeUpdatePhone,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_employee),
):
    emp = db.query(Employee).filter_by(id=emp_id, owner_id=current_user.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    emp.phone = data.phone
    db.commit()
    db.refresh(emp)
    return emp

# PUT /employees/{emp_id}/password
@router.put("/{emp_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def update_password(
    emp_id: int,
    data: EmployeeUpdatePassword,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_employee),
):
    emp = db.query(Employee).filter_by(id=emp_id, owner_id=current_user.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    emp.password_hash = pwd_context.hash(data.password)
    db.commit()

# POST /employees/{emp_id}/block
@router.post("/{emp_id}/block", status_code=status.HTTP_204_NO_CONTENT)
def block_employee(
    emp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_employee),
):
    emp = db.query(Employee).filter_by(id=emp_id, owner_id=current_user.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    emp.is_blocked = True
    db.commit()

# POST /employees/{emp_id}/unblock
@router.post("/{emp_id}/unblock", status_code=status.HTTP_204_NO_CONTENT)
def unblock_employee(
    emp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_employee),
):
    emp = db.query(Employee).filter_by(id=emp_id, owner_id=current_user.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    emp.is_blocked = False
    db.commit()

# DELETE /employees/{emp_id}
@router.delete("/{emp_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_employee(
    emp_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_employee),
):
    emp = db.query(Employee).filter_by(id=emp_id, owner_id=current_user.id).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Сотрудник не найден")
    db.delete(emp)
    db.commit()