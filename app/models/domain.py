"""
app/models/domain.py — Tool I/O için Pydantic domain modelleri

Kural: Bu modeller LLM'e olduğu gibi gider. PII (müşteri adı, telefon, e-posta,
adres) YOKTUR — sadece customer_id gibi anonim referanslar taşınır.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

# ── Enum'lar ──────────────────────────────────────────────────────────────────


class OrderStatus(StrEnum):
    CREATED = "created"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class ShipmentStatus(StrEnum):
    CREATED = "created"
    PICKED_UP = "picked_up"
    IN_TRANSIT = "in_transit"
    BRANCH_ARRIVED = "branch_arrived"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    RETURNED = "returned"


class Carrier(StrEnum):
    ARAS = "Aras"
    MNG = "MNG"
    YURTICI = "Yurtiçi"
    PTT = "PTT"
    SURAT = "Sürat"
    HEPSIJET = "HepsiJET"


# ── Tool I/O modelleri (LLM'e gidecek olanlar) ───────────────────────────────


class OrderInfo(BaseModel):
    """get_order tool çıktısı.

    customer_name YOK — PII layer kuralı: LLM prompt'una müşteri adı/telefonu
    ulaşmamalı; müşteri yalnızca customer_id ile referans edilir.
    """

    model_config = ConfigDict(from_attributes=True)

    order_id: int
    customer_id: int
    status: OrderStatus
    total: Decimal
    created_at: datetime
    has_shipment: bool
    tracking_id: str | None = None


class ShipmentInfo(BaseModel):
    """get_shipment tool çıktısı."""

    model_config = ConfigDict(from_attributes=True)

    tracking_id: str
    carrier: Carrier
    status: ShipmentStatus
    current_branch: str | None
    last_status_change_at: datetime
    eta: date | None


class ShipmentAnomaly(BaseModel):
    """list_shipments_anomaly tool çıktısı — proaktif kargo taraması için."""

    model_config = ConfigDict(from_attributes=True)

    order_id: int
    customer_id: int
    tracking_id: str
    carrier: Carrier
    current_branch: str | None
    waited_hours: int


class LowStockItem(BaseModel):
    """list_low_stock tool çıktısı — stok taraması için."""

    model_config = ConfigDict(from_attributes=True)

    sku: str
    name: str
    current_qty: int
    threshold: int
    supplier_email: str
    supplier_name: str


class SupplierEmailDraft(BaseModel):
    """prepare_supplier_email sub-agent output_type'ı."""

    subject: str
    body: str
    to_email: str
    sku: str
    suggested_qty: int


# ── Messaging tool dönüş tipi ─────────────────────────────────────────────────


class MessageDispatchResult(BaseModel):
    """Messaging tool'larının agent'a döndüğü structured sonuç.

    Exception yerine structured result döner; LLM beklenmedik durumu
    graceful handle eder.
    """

    status: Literal[
        "sent",
        "skipped_duplicate",
        "skipped_no_chat_id",
        "skipped_blocked",  # Telegram Forbidden — kullanıcı bot'u block etmiş
        "skipped_no_anomaly",  # send_owner_summary: items boş
        "skipped_telegram_error",  # genel TelegramError
    ]
    channel: Literal["tg_customer", "tg_owner", "email"]
    entity_ref: str  # order_id veya sku, debug için
    detail: str | None = None


# ── ProactiveJobsAgent output_type ───────────────────────────────────────────


class ProactiveRunSummary(BaseModel):
    """ProactiveJobsAgent'ın structured final çıktısı.

    /demo/trigger-jobs endpoint'i bu nesneyi HTTP response'a serialize eder.
    """

    anomalies_detected: int
    anomaly_messages_sent: int
    anomalies_skipped_duplicate: int
    anomalies_skipped_no_chat: int
    low_stock_detected: int
    low_stock_drafts_sent: int
    low_stock_skipped_duplicate: int


# ── Sabah Brifingi modelleri ───────────────────────────────────────────────


class OrderSummary(BaseModel):
    """list_orders_summary tool çıktısı — sabah brifinginde sipariş özeti için.

    PII içermez; customer_id anonim referans olarak taşınır.
    """

    order_id: int
    status: OrderStatus
    created_at: datetime
    has_shipment: bool


class ActiveShipmentInfo(BaseModel):
    """list_active_shipments tool çıktısı — sabah brifinginde kargo özeti için."""

    tracking_id: str
    carrier: Carrier
    status: ShipmentStatus
    current_branch: str | None
    eta: date | None
    is_delayed: bool  # last_status_change_at > 24 saat


class BriefingSummary(BaseModel):
    """MorningBriefingAgent'ın structured final çıktısı.

    /demo/trigger-briefing endpoint'i bu nesneyi HTTP response'a serialize eder.
    """

    briefing_date: date
    order_count: int
    active_shipment_count: int
    delayed_shipment_count: int
    low_stock_count: int
    message_sent: bool
