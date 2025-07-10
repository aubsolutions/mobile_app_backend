from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Invoice, Item
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

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
    status: str
    paid_amount: Optional[int] = 0
    items: List[ItemCreate]

# ----------------------
# POST: создать накладную
# ----------------------
@router.post("/invoices/")
def create_invoice(invoice: InvoiceCreate, db: Session = Depends(get_db)):
    print("🔥 Получена накладная:", invoice.dict())
def create_invoice(invoice: InvoiceCreate, db: Session = Depends(get_db)):
    db_invoice = Invoice(
        client=invoice.client,
        status=invoice.status,
        paid_amount=invoice.paid_amount,
        created_at=datetime.now()
    )
    db.add(db_invoice)
    db.commit()
    db.refresh(db_invoice)

    for item in invoice.items:
        db_item = Item(
            invoice_id=db_invoice.id,
            name=item.name,
            quantity=item.quantity,
            price=item.price
        )
        db.add(db_item)

    db.commit()
    return {"message": "Invoice created", "invoice_id": db_invoice.id}

# ----------------------
# GET: список накладных
# ----------------------
@router.get("/invoices/")
def get_invoices(db: Session = Depends(get_db)):
    invoices = db.query(Invoice).all()
    result = []
    for inv in invoices:
        result.append({
            "id": inv.id,
            "client": inv.client,
            "status": inv.status,
            "paid_amount": inv.paid_amount,
            "created_at": inv.created_at,
            "items": [{"name": item.name, "quantity": item.quantity, "price": item.price}
                      for item in inv.items]
        })
    return result
