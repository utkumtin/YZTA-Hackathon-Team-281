"""
app/api/demo.py — Demo kontrol endpoint'leri

/demo/reset: tabloları temizleyip seed fixture verilerini yükler.
/demo/set-anomaly: belirli bir kargoyu anomaly senaryosuna sokar.
/demo/trigger-jobs: ProactiveJobsAgent'ı manuel tetikler.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.deps import AgentDeps
from app.config import settings
from app.db import AsyncSessionLocal
from app.models.tables import (
    Customer,
    KBDocument,
    NotificationLog,
    Order,
    OutgoingEmail,
    Product,
    Shipment,
    Stock,
    Supplier,
)
from app.seed.fixtures import (
    get_customer_fixtures,
    get_order_fixtures,
    get_product_fixtures,
    get_shipment_fixtures,
    get_stock_fixtures,
    get_supplier_fixtures,
)

router = APIRouter(prefix="/demo", tags=["demo"])


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as db:
        yield db


class SetAnomalyRequest(BaseModel):
    shipment_id: int = Field(..., ge=1)
    hours_old: int = Field(default=12, ge=1, le=240)


@router.post("/reset", summary="Demo verilerini sıfırla")
async def reset_demo(db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    """Demo tablolarını temizler ve seed verilerini sıfırdan yükler.

    OWNER_TELEGRAM_ID seed verisi olarak DB'ye yazılmaz. Patron chat id değeri
    sadece .env -> settings.owner_telegram_id üzerinden okunur.
    """

    if not settings.demo_mode_enabled:
        raise HTTPException(status_code=403, detail="Demo mode is disabled")

    # PostgreSQL kullanıldığı için TRUNCATE en temiz yöntemdir. RESTART IDENTITY
    # sequence'leri sıfırlar, CASCADE FK bağımlılıklarını temizler.
    await db.execute(
        text(
            """
            TRUNCATE TABLE
                kb_documents,
                outgoing_emails,
                notification_log,
                shipments,
                orders,
                stock,
                products,
                suppliers,
                customers
            RESTART IDENTITY CASCADE
            """
        )
    )

    customers = get_customer_fixtures()
    suppliers = get_supplier_fixtures()
    products = get_product_fixtures()
    stock = get_stock_fixtures()
    orders = get_order_fixtures()
    shipments = get_shipment_fixtures()

    db.add_all([Customer(**item) for item in customers])
    db.add_all([Supplier(**item) for item in suppliers])
    db.add_all([Product(**item) for item in products])
    db.add_all([Stock(**item) for item in stock])
    db.add_all([Order(**item) for item in orders])
    db.add_all([Shipment(**item) for item in shipments])

    await db.commit()

    return {
        "status": "ok",
        "inserted": {
            "customers": len(customers),
            "suppliers": len(suppliers),
            "products": len(products),
            "stock": len(stock),
            "orders": len(orders),
            "shipments": len(shipments),
        },
        "owner_telegram_id_from_env": bool(settings.owner_telegram_id),
    }


@router.post("/set-anomaly", summary="Kargoyu anomali durumuna sok")
async def set_anomaly(
    payload: SetAnomalyRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Belirli bir shipment kaydını anomaly testine uygun hale getirir."""

    if not settings.demo_mode_enabled:
        raise HTTPException(status_code=403, detail="Demo mode is disabled")

    anomaly_time = datetime.now(timezone.utc) - \
        timedelta(hours=payload.hours_old)

    result = await db.execute(
        update(Shipment)
        .where(Shipment.id == payload.shipment_id)
        .values(
            status="in_transit",
            last_status_change_at=anomaly_time,
            current_branch="Transfer Merkezi - Güncelleme Bekliyor",
        )
    )

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Shipment not found")

    await db.commit()

    return {
        "status": "ok",
        "shipment_id": payload.shipment_id,
        "new_status": "in_transit",
        "last_status_change_at": anomaly_time.isoformat(),
    }


@router.post("/trigger-jobs", summary="ProactiveJobsAgent manuel tetikleme")
async def trigger_jobs(db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    """Demo sırasında proaktif agent'ı elle çalıştırmak için yardımcı endpoint."""

    if not settings.demo_mode_enabled:
        raise HTTPException(status_code=403, detail="Demo mode is disabled")

    from app.agents.proactive_jobs import run_proactive_jobs

    deps = AgentDeps(
        db=db,
        owner_chat_id=settings.owner_telegram_id,
        bot_token=settings.telegram_bot_token,
    )

    summary = await run_proactive_jobs(deps)

    return summary.model_dump()


@router.post("/trigger-briefing", summary="Sabah brifingini manuel tetikle")
async def trigger_briefing(db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    """Demo sırasında sabah brifingini elle çalıştırmak için yardımcı endpoint.

    Production'da bu endpoint APScheduler ile 08:00'de otomatik tetiklenir.
    """

    if not settings.demo_mode_enabled:
        raise HTTPException(status_code=403, detail="Demo mode is disabled")

    from app.agents.proactive_jobs import run_morning_briefing

    deps = AgentDeps(
        db=db,
        owner_chat_id=settings.owner_telegram_id,
        bot_token=settings.telegram_bot_token,
    )

    summary = await run_morning_briefing(deps)

    return summary.model_dump()
