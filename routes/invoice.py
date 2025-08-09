# routes/invoice.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import SessionLocal
from models import Invoice, Item, Client, User, Employee, Product
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from fastapi.responses import HTMLResponse
from routes.auth import get_actor  # универсальный актёр (владелец/сотрудник)

router = APIRouter()

# ----------------------
# Подключение к БД
# ----------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ----------------------
# Pydantic-схемы
# ----------------------
class ItemCreate(BaseModel):
    name: str
    quantity: int
    price: int

class InvoiceCreate(BaseModel):
    client: str
    phone: str
    status: str
    paid_amount: Optional[int] = 0
    items: List[ItemCreate]

class FeedbackCreate(BaseModel):
    message: str
    name: Optional[str] = None

# ----------------------
# Генерация номера накладной
# ----------------------
def generate_invoice_number(db, client_id: int):
    year = datetime.now().year
    count = db.query(func.count()).select_from(Invoice).filter(
        Invoice.client_id == client_id,
        func.extract('year', Invoice.created_at) == year
    ).scalar() or 0
    return f"№{str(client_id).zfill(4)}/{year}/{count + 1}"

# ----------------------
# Хелпер: upsert товара в номенклатуру владельца
# ----------------------
def upsert_product(db: Session, owner_id: int, name: str, price: int):
    name = (name or "").strip()
    if not name:
        return
    # важно: в таблице products колонка user_id, а не owner_id
    product = db.query(Product).filter(
        Product.user_id == owner_id,
        func.lower(Product.name) == name.lower()
    ).first()
    if product:
        # стратегия "последняя цена побеждает"
        product.price = price
        # если в модели есть updated_at — обновим
        if hasattr(product, "updated_at"):
            product.updated_at = datetime.utcnow()
    else:
        kwargs = dict(user_id=owner_id, name=name, price=price)
        # если в модели есть поля дат — проставим
        if hasattr(Product, "created_at"):
            kwargs["created_at"] = datetime.utcnow()
        if hasattr(Product, "updated_at"):
            kwargs["updated_at"] = datetime.utcnow()
        db.add(Product(**kwargs))

# ----------------------
# POST: создать накладную (владелец или сотрудник)
# ----------------------
@router.post("/invoices/")
def create_invoice(
    invoice: InvoiceCreate,
    db: Session = Depends(get_db),
    actor = Depends(get_actor),
):
    try:
        # 1. Найти/создать клиента
        client = db.query(Client).filter_by(phone=invoice.phone).first()
        if not client:
            client = Client(name=invoice.client, phone=invoice.phone)
            db.add(client)
            db.commit()
            db.refresh(client)

        # 2. Сгенерировать номер накладной
        invoice_number = generate_invoice_number(db, client.id)

        # 3. Определить владельца и продавца
        if actor["role"] == "user":
            owner_id = actor["user"].id
            seller_employee_id = None
            seller_name = actor["user"].name
        else:
            emp: Employee = actor["employee"]
            owner_id = emp.owner_id
            seller_employee_id = emp.id
            seller_name = emp.name

        # 4. Создать накладную
        db_invoice = Invoice(
            client=invoice.client,
            client_id=client.id,
            invoice_number=invoice_number,
            status=invoice.status,
            paid_amount=invoice.paid_amount or 0,
            created_at=datetime.now(),
            user_id=owner_id,
            seller_employee_id=seller_employee_id,
            seller_name=seller_name,
        )
        db.add(db_invoice)
        db.commit()
        db.refresh(db_invoice)

        # 5. Добавить товары + попутно апсертить номенклатуру
        for item in invoice.items:
            db_item = Item(
                invoice_id=db_invoice.id,
                name=item.name,
                quantity=item.quantity,
                price=item.price
            )
            db.add(db_item)
            # апсерт товара в справочник организации
            upsert_product(db, owner_id, item.name, item.price)

        # один общий коммит на все позиции и апсерты
        db.commit()

        # 6. Ответ
        return {
            "message": "Invoice created",
            "invoice_id": db_invoice.id,
            "invoice_number": db_invoice.invoice_number,
            "seller_employee_id": db_invoice.seller_employee_id,
            "seller_name": db_invoice.seller_name,
        }

    except Exception as e:
        db.rollback()
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Ошибка сохранения накладной: {e}")

# ----------------------
# Вспомогательная функция: список накладных
# ----------------------
def _list_invoices(db: Session, actor, seller_employee_id: Optional[int]):
    if actor["role"] == "user":
        q = db.query(Invoice).filter(Invoice.user_id == actor["user"].id)
        if seller_employee_id is not None:
            q = q.filter(Invoice.seller_employee_id == seller_employee_id)
        invoices = q.all()
    else:
        emp: Employee = actor["employee"]
        invoices = db.query(Invoice).filter(
            Invoice.user_id == emp.owner_id,
            Invoice.seller_employee_id == emp.id
        ).all()

    result = []
    for inv in invoices:
        result.append({
            "id": inv.id,
            "client": inv.client,
            "phone": inv.client_rel.phone if inv.client_rel else None,
            "status": inv.status,
            "paid_amount": inv.paid_amount,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
            "invoice_number": inv.invoice_number,
            "seller_employee_id": getattr(inv, "seller_employee_id", None),
            "seller_name": getattr(inv, "seller_name", None),
            "items": [
                {"name": item.name, "quantity": item.quantity, "price": item.price}
                for item in inv.items
            ],
        })
    return result

@router.get("/invoices/")
def get_invoices_slash(
    db: Session = Depends(get_db),
    actor = Depends(get_actor),
    seller_employee_id: Optional[int] = Query(None),
):
    return _list_invoices(db, actor, seller_employee_id)

@router.get("/invoices")
def get_invoices_no_slash(
    db: Session = Depends(get_db),
    actor = Depends(get_actor),
    seller_employee_id: Optional[int] = Query(None),
):
    return _list_invoices(db, actor, seller_employee_id)

# ----------------------
# Публичная страница накладной (QR-код)
# ----------------------
@router.get("/invoice/{invoice_id}", response_class=HTMLResponse)
def public_invoice_page(invoice_id: int):
    db = SessionLocal()
    invoice = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    db.close()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    supplier = getattr(invoice, "supplier_name", None)
    if not supplier:
        supplier = getattr(invoice, "client", "—")

    number = getattr(invoice, "invoice_number", invoice.id)

    return f"""
    <html>
    <head>
      <title>Накладная #{number}</title>
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <style>
        body {{ font-family: Arial, sans-serif; max-width: 400px; margin: 50px auto; background: #f7f7f7; }}
        .card {{ background: #fff; padding: 24px; border-radius: 10px; box-shadow: 0 4px 16px #0001; }}
        .title {{ font-size: 22px; font-weight: bold; margin-bottom: 8px; }}
        .subtitle {{ color: #888; margin-bottom: 12px; }}
      </style>
    </head>
    <body>
      <div class="card">
        <div class="title">Поставщик: {supplier}</div>
        <div class="subtitle">Накладная №{number}</div>
      </div>
    </body>
    </html>
    """