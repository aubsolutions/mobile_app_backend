from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import SessionLocal
from models import Invoice, Item, Client, User
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from routes.auth import get_current_user
from fastapi.responses import HTMLResponse  # 👈 важно

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
# POST: создать накладную
# ----------------------
@router.post("/invoices/")
def create_invoice(
    invoice: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. Найти клиента по номеру телефона
    client = db.query(Client).filter_by(phone=invoice.phone).first()

    # 2. Если клиента нет — создать
    if not client:
        client = Client(name=invoice.client, phone=invoice.phone)
        db.add(client)
        db.commit()
        db.refresh(client)

    # 3. Сгенерировать номер накладной
    invoice_number = generate_invoice_number(db, client.id)

    # 4. Создать накладную
    db_invoice = Invoice(
        client=invoice.client,
        client_id=client.id,
        invoice_number=invoice_number,
        status=invoice.status,
        paid_amount=invoice.paid_amount,
        created_at=datetime.now(),
        user_id=current_user.id,
    )
    db.add(db_invoice)
    db.commit()
    db.refresh(db_invoice)

    # 5. Добавить товары
    for item in invoice.items:
        db_item = Item(
            invoice_id=db_invoice.id,
            name=item.name,
            quantity=item.quantity,
            price=item.price
        )
        db.add(db_item)

    db.commit()
    return {
        "message": "Invoice created",
        "invoice_id": db_invoice.id,
        "invoice_number": db_invoice.invoice_number
    }

# ----------------------
# GET: список накладных (ТОЛЬКО пользователя)
# ----------------------
@router.get("/invoices/")
def get_invoices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    invoices = db.query(Invoice).filter_by(user_id=current_user.id).all()
    result = []
    for inv in invoices:
        result.append({
            "id": inv.id,
            "client": inv.client,
            "phone": inv.client_rel.phone if inv.client_rel else None,
            "status": inv.status,
            "paid_amount": inv.paid_amount,
            "created_at": inv.created_at.isoformat(),
            "invoice_number": inv.invoice_number,
            "items": [{"name": item.name, "quantity": item.quantity, "price": item.price}
                      for item in inv.items]
        })
    return result

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
    # Фолбэк на client, если supplier_name нет:
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

