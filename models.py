# ✅ models.py
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
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
    status = Column(String, default="не оплачен")
    created_at = Column(DateTime, default=datetime.utcnow)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    invoice_number = Column(String, unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)  # 👈 Привязка к пользователю

    client_rel = relationship("Client", back_populates="invoices")
    items = relationship("Item", back_populates="invoice", cascade="all, delete")
    user = relationship("User", back_populates="invoices")


class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"))
    name = Column(String, nullable=False)
    quantity = Column(Integer, nullable=False)
    price = Column(Integer, nullable=False)

    invoice = relationship("Invoice", back_populates="items")


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False, unique=True)

    invoices = relationship("Invoice", back_populates="client_rel")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    company = Column(String, nullable=True)
    email = Column(String, unique=True, nullable=False)
    phone = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    plan = Column(String, default="free")
    plan_expires = Column(DateTime, nullable=True)
    payment_status = Column(String, default="нет данных")
    terms_accepted_at = Column(DateTime, nullable=True)
    invoices = relationship("Invoice", back_populates="user")

class Feedback(Base):
    __tablename__ = "feedbacks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # опционально, если будет анонимный отзыв
    name = Column(String, nullable=True)      # имя отправителя (если надо)
    message = Column(String, nullable=False)  # текст отзыва
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="feedbacks")

