# routes/products.py

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional, Dict, Any

from database import get_db
from routes.auth import get_actor
from models import Product, User, Employee

router = APIRouter()


# ───────────────────────────────────────────────────────────────────────────────
# Вспомогательные
# ───────────────────────────────────────────────────────────────────────────────
def _owner_id_from_actor(actor: Dict[str, Any]) -> int:
    """Возвращает owner_id для организации (владелец или владелец сотрудника)."""
    if actor["role"] == "user":
        return actor["user"].id  # type: ignore
    return actor["employee"].owner_id  # type: ignore


def _normalize_name(name: str) -> str:
    return (name or "").strip()


def _product_to_dict(p: Product) -> Dict[str, Any]:
    return {"id": p.id, "name": p.name, "price": p.price}


def _list_products(db: Session, actor: Dict[str, Any], q: Optional[str]) -> list[Dict[str, Any]]:
    owner_id = _owner_id_from_actor(actor)
    query = db.query(Product).filter(Product.user_id == owner_id)
    if q:
        q = q.strip()
        if q:
            query = query.filter(Product.name.ilike(f"%{q}%"))
    products = query.order_by(Product.name.asc()).all()
    return [_product_to_dict(p) for p in products]


# ───────────────────────────────────────────────────────────────────────────────
# GET /products/  — список с поиском
# ───────────────────────────────────────────────────────────────────────────────
@router.get("/products/")
def get_products_slash(
    q: Optional[str] = Query(None, description="Поиск по названию"),
    db: Session = Depends(get_db),
    actor=Depends(get_actor),
):
    return _list_products(db, actor, q)


# Дубликат без слеша, чтобы не было 307 редиректа
@router.get("/products")
def get_products_no_slash(
    q: Optional[str] = Query(None, description="Поиск по названию"),
    db: Session = Depends(get_db),
    actor=Depends(get_actor),
):
    return _list_products(db, actor, q)


# ───────────────────────────────────────────────────────────────────────────────
# POST /products/ — создать (или обновить цену, если товар с тем же именем уже есть)
# ───────────────────────────────────────────────────────────────────────────────
from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    name: str = Field(..., min_length=1)
    price: int = Field(ge=0)


def _create_or_update_product(
    db: Session, actor: Dict[str, Any], data: ProductCreate
) -> Dict[str, Any]:
    owner_id = _owner_id_from_actor(actor)
    name = _normalize_name(data.name)
    if not name:
        raise HTTPException(status_code=400, detail="Название товара не может быть пустым")

    # Ищем по имени без учета регистра в рамках организации
    existing = (
        db.query(Product)
        .filter(
            Product.user_id == owner_id,
            func.lower(Product.name) == func.lower(name),
        )
        .first()
    )
    if existing:
        # Если уже есть — просто обновим цену (удобно для "добавления вручную" одинакового названия)
        if existing.price != data.price:
            existing.price = data.price
            db.commit()
            db.refresh(existing)
        return _product_to_dict(existing)

    # Иначе создаём новый
    p = Product(user_id=owner_id, name=name, price=data.price)
    db.add(p)
    db.commit()
    db.refresh(p)
    return _product_to_dict(p)


@router.post("/products/")
def create_product_slash(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    actor=Depends(get_actor),
):
    return _create_or_update_product(db, actor, payload)


# Дубликат без слеша
@router.post("/products")
def create_product_no_slash(
    payload: ProductCreate,
    db: Session = Depends(get_db),
    actor=Depends(get_actor),
):
    return _create_or_update_product(db, actor, payload)


# ───────────────────────────────────────────────────────────────────────────────
# PUT /products/{product_id} — обновить имя/цену
# ───────────────────────────────────────────────────────────────────────────────
class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    price: Optional[int] = Field(None, ge=0)


def _update_product(
    db: Session, actor: Dict[str, Any], product_id: int, data: ProductUpdate
) -> Dict[str, Any]:
    owner_id = _owner_id_from_actor(actor)
    p = db.query(Product).filter(Product.id == product_id, Product.user_id == owner_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Товар не найден")

    # Если меняем название — проверим уникальность внутри организации (без регистра)
    if data.name is not None:
        new_name = _normalize_name(data.name)
        if not new_name:
            raise HTTPException(status_code=400, detail="Название товара не может быть пустым")

        conflict = (
            db.query(Product)
            .filter(
                Product.user_id == owner_id,
                func.lower(Product.name) == func.lower(new_name),
                Product.id != product_id,
            )
            .first()
        )
        if conflict:
            raise HTTPException(status_code=409, detail="Товар с таким названием уже существует")
        p.name = new_name

    if data.price is not None:
        p.price = data.price

    db.commit()
    db.refresh(p)
    return _product_to_dict(p)


@router.put("/products/{product_id}")
def update_product_no_slash(
    product_id: int,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    actor=Depends(get_actor),
):
    return _update_product(db, actor, product_id, payload)


@router.put("/products/{product_id}/")
def update_product_slash(
    product_id: int,
    payload: ProductUpdate,
    db: Session = Depends(get_db),
    actor=Depends(get_actor),
):
    return _update_product(db, actor, product_id, payload)


# ───────────────────────────────────────────────────────────────────────────────
# (Опционально) GET /products/{product_id} — получить по id
# ───────────────────────────────────────────────────────────────────────────────
def _get_product(db: Session, actor: Dict[str, Any], product_id: int) -> Dict[str, Any]:
    owner_id = _owner_id_from_actor(actor)
    p = db.query(Product).filter(Product.id == product_id, Product.user_id == owner_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Товар не найден")
    return _product_to_dict(p)


@router.get("/products/{product_id}")
def get_product_no_slash(
    product_id: int,
    db: Session = Depends(get_db),
    actor=Depends(get_actor),
):
    return _get_product(db, actor, product_id)


@router.get("/products/{product_id}/")
def get_product_slash(
    product_id: int,
    db: Session = Depends(get_db),
    actor=Depends(get_actor),
):
    return _get_product(db, actor, product_id)