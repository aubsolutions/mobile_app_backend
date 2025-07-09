from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean, Float
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    client = Column(String, nullable=False)
    amount = Column(Integer, nullable=False, default=0)
    paid_amount = Column(Integer, nullable=True, default=0)
    status = Column(String, default="не оплачен")  # "оплачен" или "не оплачен"
    created_at = Column(DateTime, default=datetime.utcnow)

    items = relationship("Item", back_populates="invoice", cascade="all, delete")

class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"))
    name = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Integer, nullable=False)

    invoice = relationship("Invoice", back_populates="items")
