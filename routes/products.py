# routes/products.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from pydantic import BaseModel

from database import SessionLocal
from models import Product, User, Employee
from routes.auth import get_actor  # определяем владельца по токену

router = APIRouter(prefix="/products", tags=["products"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ------- схемы -------
class ProductCreate(BaseModel):
    name: str
    price: int

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[int] = None

class ProductOut(BaseModel):
    id: int
    name: str
    price: int
    class Config:
        orm_mode = True

def _owner_id_from_actor(actor) -> int:
    if actor["role"] == "user":
        return actor["user"].id
    else:
        return actor["employee"].owner_id

# ------- список всех товаров (организации) -------
@router.get("/", response_model=List[ProductOut])
def list_products(
    db: Session = Depends(get_db),
    actor = Depends(get_actor),
):
    owner_id = _owner_id_from_actor(actor)
    prods = db.query(Product).filter(Product.owner_id == owner_id).order_by(func.lower(Product.name)).all()
    return prods

# дублируем без слэша, чтобы не ловить 307
@router.get("", response_model=List[ProductOut])
def list_products_noslash(
    db: Session = Depends(get_db),
    actor = Depends(get_actor),
):
    return list_products(db, actor)  # type: ignore

# ------- поиск по названию (подсказки) -------
@router.get("/search", response_model=List[ProductOut])
def search_products(
    q: str = Query(""),
    db: Session = Depends(get_db),
    actor = Depends(get_actor),
):
    owner_id = _owner_id_from_actor(actor)
    query = db.query(Product).filter(Product.owner_id == owner_id)
    if q:
        query = query.filter(func.lower(Product.name).like(f"%{q.lower()}%"))
    return query.order_by(func.lower(Product.name)).limit(50).all()

# ------- создать вручную -------
@router.post("/", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    data: ProductCreate,
    db: Session = Depends(get_db),
    actor = Depends(get_actor),
):
    owner_id = _owner_id_from_actor(actor)
    # Проверяем уникальность имени в рамках владельца (без учёта регистра)
    exists = db.query(Product).filter(
        Product.owner_id == owner_id,
        func.lower(Product.name) == func.lower(data.name)
    ).first()
    if exists:
        raise HTTPException(status_code=400, detail="Товар с таким названием уже существует")

    p = Product(owner_id=owner_id, name=data.name.strip(), price=data.price)
    db.add(p)
    db.commit()
    db.refresh(p)
    return p

# ------- обновить (название/цену) -------
@router.put("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int,
    data: ProductUpdate,
    db: Session = Depends(get_db),
    actor = Depends(get_actor),
):
    owner_id = _owner_id_from_actor(actor)
    p = db.query(Product).filter(Product.id == product_id, Product.owner_id == owner_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Товар не найден")

    if data.name is not None:
        # не даём дублировать имена в рамках владельца
        dup = db.query(Product).filter(
            Product.owner_id == owner_id,
            func.lower(Product.name) == func.lower(data.name),
            Product.id != product_id
        ).first()
        if dup:
            raise HTTPException(status_code=400, detail="Товар с таким названием уже существует")
        p.name = data.name.strip()
    if data.price is not None:
        p.price = data.price

    db.commit()
    db.refresh(p)
    return p