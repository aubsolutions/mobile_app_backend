# routes/products.py
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import List, Optional

from database import get_db
from models import Product, User, Employee
from routes.auth import get_actor  # {"role": "user"/"employee", "user"/"employee": obj}

router = APIRouter(prefix="/products", tags=["products"])

# ───────────────────────────────────────────────────────────────────────────────
# Pydantic
# ───────────────────────────────────────────────────────────────────────────────
class ProductCreate(BaseModel):
    name: str
    price: int

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[int] = None

class ProductOut(BaseModel):
    id: int
    name: str
    last_price: int
    class Config:
        orm_mode = True

# ───────────────────────────────────────────────────────────────────────────────
# helpers
# ───────────────────────────────────────────────────────────────────────────────
def _owner_id_from_actor(actor) -> int:
    if actor["role"] == "user":
        return actor["user"].id
    else:
        emp: Employee = actor["employee"]
        return emp.owner_id

# ───────────────────────────────────────────────────────────────────────────────
# GET /products — список с поиском
# ───────────────────────────────────────────────────────────────────────────────
@router.get("/", response_model=List[ProductOut])
def list_products(
    q: Optional[str] = Query(None, description="Поиск по названию"),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    actor = Depends(get_actor),
):
    owner_id = _owner_id_from_actor(actor)
    query = db.query(Product).filter(Product.user_id == owner_id)

    if q:
        q_like = f"%{q.lower()}%"
        query = query.filter(func.lower(Product.name).like(q_like))

    products = query.order_by(Product.name.asc()).offset(offset).limit(limit).all()
    return products

# ───────────────────────────────────────────────────────────────────────────────
# POST /products — ручное добавление
# ───────────────────────────────────────────────────────────────────────────────
@router.post("/", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    data: ProductCreate,
    db: Session = Depends(get_db),
    actor = Depends(get_actor),
):
    owner_id = _owner_id_from_actor(actor)

    # уникальность имени в рамках владельца
    exists = db.query(Product).filter(
        Product.user_id == owner_id,
        func.lower(Product.name) == func.lower(data.name.strip())
    ).first()
    if exists:
        raise HTTPException(status_code=400, detail="Такой товар уже есть в номенклатуре")

    prod = Product(
        user_id=owner_id,
        name=data.name.strip(),
        last_price=int(data.price or 0),
    )
    db.add(prod)
    db.commit()
    db.refresh(prod)
    return prod

# ───────────────────────────────────────────────────────────────────────────────
# PUT /products/{product_id} — изменить имя/цену
# ───────────────────────────────────────────────────────────────────────────────
@router.put("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int,
    data: ProductUpdate,
    db: Session = Depends(get_db),
    actor = Depends(get_actor),
):
    owner_id = _owner_id_from_actor(actor)
    prod = db.query(Product).filter(Product.id == product_id, Product.user_id == owner_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Товар не найден")

    if data.name is not None:
        new_name = data.name.strip()
        # проверим уникальность нового имени
        dup = db.query(Product).filter(
            Product.user_id == owner_id,
            func.lower(Product.name) == func.lower(new_name),
            Product.id != product_id
        ).first()
        if dup:
            raise HTTPException(status_code=400, detail="Товар с таким названием уже существует")
        prod.name = new_name

    if data.price is not None:
        prod.last_price = int(data.price)

    prod.updated_at = func.now()
    db.commit()
    db.refresh(prod)
    return prod

# ───────────────────────────────────────────────────────────────────────────────
# DELETE /products/{product_id} — (опционально)
# ───────────────────────────────────────────────────────────────────────────────
@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    actor = Depends(get_actor),
):
    owner_id = _owner_id_from_actor(actor)
    prod = db.query(Product).filter(Product.id == product_id, Product.user_id == owner_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Товар не найден")
    db.delete(prod)
    db.commit()