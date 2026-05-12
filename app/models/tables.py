"""
app/models/tables.py — SQLAlchemy ORM tablo modelleri

Bu modeller scripts/init_db.sql içindeki PostgreSQL şemasıyla uyumludur.
Alembic/migration yerine mevcut init_db.sql kullanıldığı için burada tablo
oluşturma mantığı yoktur; tool'lar ve endpoint'ler ORM üzerinden sorgu yapmak
için bu sınıfları kullanır.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Tüm ORM modelleri için declarative base."""


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(120))
    telegram_chat_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    orders: Mapped[list["Order"]] = relationship(back_populates="customer")


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    products: Mapped[list["Product"]] = relationship(back_populates="supplier")


class Product(Base):
    __tablename__ = "products"

    sku: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    supplier_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("suppliers.id"))
    price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    supplier: Mapped[Supplier | None] = relationship(back_populates="products")
    stock: Mapped["Stock | None"] = relationship(
        back_populates="product", uselist=False)


class Stock(Base):
    __tablename__ = "stock"

    sku: Mapped[str] = mapped_column(
        String(40), ForeignKey("products.sku"), primary_key=True)
    current_qty: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0)
    threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    product: Mapped[Product] = relationship(back_populates="stock")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("customers.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="created")
    total: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    customer: Mapped[Customer] = relationship(back_populates="orders")
    shipment: Mapped["Shipment | None"] = relationship(
        back_populates="order", uselist=False)


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("orders.id"), nullable=False, unique=True
    )
    tracking_id: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True)
    carrier: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="created")
    current_branch: Mapped[str | None] = mapped_column(String(120))
    last_status_change_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    eta: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    order: Mapped[Order] = relationship(back_populates="shipment")


class NotificationLog(Base):
    __tablename__ = "notification_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    notif_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_ref: Mapped[str] = mapped_column(String(40), nullable=False)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class OutgoingEmail(Base):
    __tablename__ = "outgoing_emails"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    to_email: Mapped[str] = mapped_column(String(200), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    related_sku: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="sent_mock")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class KBDocument(Base):
    __tablename__ = "kb_documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(String(60))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # embedding kolonunu ORM'de şimdilik kullanmıyoruz; pgvector tip bağımlılığına
    # takılmamak için tablo operasyonlarında bu model kullanılmayacaksa güvenli.
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
