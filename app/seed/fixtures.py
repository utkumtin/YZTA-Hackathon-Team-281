"""
app/seed/fixtures.py — Demo seed verileri

Kritik kural: OWNER_TELEGRAM_ID burada tutulmaz. Patron chat id değeri sadece
.env üzerinden app.config.settings.owner_telegram_id ile okunur.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.config import settings


def get_customer_fixtures() -> list[dict]:
    return [
        {
            "id": 1,
            "name": "Ayşe Demir",
            "phone": "+905551111111",
            "email": "ayse.demir@example.com",
            "telegram_chat_id": settings.demo_customer_tg_id or 111111111,
        },
        {
            "id": 2,
            "name": "Mehmet Kaya",
            "phone": "+905552222222",
            "email": "mehmet.kaya@example.com",
            "telegram_chat_id": None,
        },
    ]


def get_supplier_fixtures() -> list[dict]:
    return [
        {
            "id": 1,
            "name": "Anadolu Kumaş Tedarik",
            "email": "tedarik@anadolukumas.example.com",
            "phone": "+902121111111",
        },
        {
            "id": 2,
            "name": "Marmara Ambalaj",
            "email": "sales@marmaraambalaj.example.com",
            "phone": "+902122222222",
        },
        {
            "id": 3,
            "name": "Ege Tekstil Hammadde",
            "email": "info@egetekstil.example.com",
            "phone": "+902323333333",
        },
    ]


def get_product_fixtures() -> list[dict]:
    return [
        {
            "sku": "KMS-001",
            "name": "Pamuk Kumaş",
            "description": "Üretimde kullanılan ana pamuk kumaş stoğu.",
            "supplier_id": 1,
            "price": Decimal("120.00"),
        },
        {
            "sku": "IPL-002",
            "name": "Dikiş İpliği Seti",
            "description": "Standart üretim hattı için iplik seti.",
            "supplier_id": 3,
            "price": Decimal("35.50"),
        },
        {
            "sku": "AMB-003",
            "name": "Kargo Ambalaj Kutusu",
            "description": "E-ticaret gönderileri için dayanıklı kutu.",
            "supplier_id": 2,
            "price": Decimal("8.75"),
        },
        {
            "sku": "ETK-004",
            "name": "Ürün Etiketi",
            "description": "Ürün paketleri için barkodlu etiket.",
            "supplier_id": 2,
            "price": Decimal("1.20"),
        },
    ]


def get_stock_fixtures() -> list[dict]:
    now = datetime.now(timezone.utc)
    return [
        {"sku": "KMS-001", "current_qty": 4, "threshold": 10, "updated_at": now},
        {"sku": "IPL-002", "current_qty": 55, "threshold": 20, "updated_at": now},
        {"sku": "AMB-003", "current_qty": 120, "threshold": 30, "updated_at": now},
        {"sku": "ETK-004", "current_qty": 80, "threshold": 25, "updated_at": now},
    ]


def get_order_fixtures() -> list[dict]:
    now = datetime.now(timezone.utc)
    return [
        {
            "id": 1,
            "customer_id": 1,
            "status": "shipped",
            "total": Decimal("860.00"),
            "created_at": now - timedelta(days=1),
            "updated_at": now - timedelta(hours=10),
        },
        {
            "id": 2,
            "customer_id": 2,
            "status": "shipped",
            "total": Decimal("420.00"),
            "created_at": now - timedelta(hours=12),
            "updated_at": now - timedelta(hours=6),
        },
    ]


def get_shipment_fixtures() -> list[dict]:
    now = datetime.now(timezone.utc)
    return [
        {
            "id": 1,
            "order_id": 1,
            "tracking_id": "TRK-DEMO-001",
            "carrier": "yurtici",
            "status": "in_transit",
            "current_branch": "İstanbul Transfer Merkezi",
            "last_status_change_at": now - timedelta(hours=9),
            "eta": date.today() + timedelta(days=1),
        },
        {
            "id": 2,
            "order_id": 2,
            "tracking_id": "TRK-DEMO-002",
            "carrier": "aras",
            "status": "delivered",
            "current_branch": "Gaziantep Şube",
            "last_status_change_at": now - timedelta(hours=1),
            "eta": date.today(),
        },
    ]
