# routes/products.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from pydantic import BaseModel

from database import get_db
from models import Product, Employee
from routes.auth import get_actor  # {"role": "user"/"employee", ...}

router = APIRouter(prefix="/products", tags=["products"])

class ProductIn(BaseModel):
    name: str
    price: int

class ProductOut(BaseModel):
    id: int
    name: str
    price: int
    class Config:
        orm_mode = True

def _owner_user_id(actor) -> int:
    if actor["role"] == "user":
        return actor["user"].id
    else:
        emp: Employee = actor["employee"]
        return emp.owner_id

@router.get("/", response_model=List[ProductOut])
def list_products(
    q: Optional[str] = Query(None, description="Поиск по названию"),
    db: Session = Depends(get_db),
    actor = Depends(get_actor),
):
    owner_id = _owner_user_id(actor)
    qs = db.query(Product).filter(Product.user_id == owner_id)
    if q:
        qs = qs.filter(func.lower(Product.name).contains(q.lower()))
    # thanks to @property price, orm_mode вернёт поле price из last_price
    return qs.order_by(func.lower(Product.name)).all()

@router.get("", response_model=List[ProductOut])
def list_products_no_slash(
    q: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    actor = Depends(get_actor),
):
    return list_products(q=q, db=db, actor=actor)

@router.post("/", response_model=ProductOut)
def create_product(
    data: ProductIn,
    db: Session = Depends(get_db),
    actor = Depends(get_actor),
):
    owner_id = _owner_user_id(actor)
    existing = db.query(Product).filter(
        Product.user_id == owner_id,
        func.lower(Product.name) == data.name.lower()
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Такой товар уже существует")

    prod = Product(
        user_id=owner_id,
        name=data.name.strip(),
        last_price=data.price,  # <— важно
    )
    db.add(prod)
    db.commit()
    db.refresh(prod)
    return prod

@router.put("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int,
    data: ProductIn,
    db: Session = Depends(get_db),
    actor = Depends(get_actor),
):
    owner_id = _owner_user_id(actor)
    prod = db.query(Product).filter(
        Product.id == product_id,
        Product.user_id == owner_id
    ).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Товар не найден")

    dup = db.query(Product).filter(
        Product.user_id == owner_id,
        func.lower(Product.name) == data.name.lower(),
        Product.id != product_id
    ).first()
    if dup:
        raise HTTPException(status_code=400, detail="Товар с таким названием уже есть")

    prod.name = data.name.strip()
    prod.last_price = data.price  # <— важно
    prod.updated_at = func.now()
    db.commit()
    db.refresh(prod)
    return prod