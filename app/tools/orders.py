from datetime import date, datetime, timedelta, timezone
from typing import Optional

from pydantic_ai import RunContext
from sqlalchemy import select

from app.agents.deps import AgentDeps
from app.models.domain import (
    Carrier,
    OrderInfo,
    OrderStatus,
    OrderSummary,
    ShipmentInfo,
    ShipmentStatus,
)

async def get_order(ctx: RunContext[AgentDeps], order_id: int) -> Optional[OrderInfo]:
    """
    Görev: order_id ile e-ticaret veritabanındaki tek bir sipariş kaydını getirir.
    Ne zaman kullanılır: Müşteri mesajında bir sipariş numarası geçtiğinde.
        Mesajda sipariş numarası YOKSA bu tool'u ÇAĞIRMA — müşteriden numarayı iste.
    Parametre: order_id (int) — Sipariş ID'si, pozitif tam sayı.
    Dönüş: OrderInfo objesi (sipariş statüsü, has_shipment, tracking_id) veya
        sipariş bulunamazsa None. Müşteri adı/telefonu DÖNMEZ.

    ÇAĞIRMA: Sipariş statüsünü tahmin etmek veya müşteri kimliği aramak için.
    """
    # TODO: Gerçek veritabanı sorgusu eklenecek.
    # Örnek SQL: result = await ctx.deps.db.execute(select(Order).where(Order.id == order_id))
    
    # Mock Data
    if order_id <= 0:
        return None
        
    return OrderInfo(
        order_id=order_id,
        customer_id=999, # Sadece ID var, isim vs yok (PII kuralı)
        status=OrderStatus.SHIPPED,
        total=1250.50,
        created_at=datetime.now() - timedelta(days=2),
        has_shipment=True,
        tracking_id=f"TRK{order_id}8899"
    )

async def get_shipment(ctx: RunContext[AgentDeps], tracking_id: str) -> Optional[ShipmentInfo]:
    """
    Görev: tracking_id ile kargo durumunu ve detaylarını getirir.
    Ne zaman kullanılır: get_order çıktısında has_shipment=True ve tracking_id doluysa çağrılır.
        has_shipment=False ise bu tool'u çağırma.
    Parametre: tracking_id (str) — Kargo takip numarası.
    Dönüş: ShipmentInfo objesi veya kargo bulunamazsa None. PII içermez.
    """
    # TODO: Gerçek veritabanı / Kargo entegrasyonu sorgusu eklenecek.
    
    # Mock Data
    if not tracking_id or tracking_id.startswith("INVALID"):
        return None
        
    return ShipmentInfo(
        tracking_id=tracking_id,
        carrier=Carrier.YURTICI,
        status=ShipmentStatus.IN_TRANSIT,
        current_branch="Kadıköy Transfer Merkezi",
        last_status_change_at=datetime.now() - timedelta(hours=5),
        eta=date.today() + timedelta(days=1)
    )


async def list_orders_summary(
    ctx: RunContext[AgentDeps],
    since_hours: int = 24,
    limit: int = 100,
) -> list[OrderSummary]:
    """
    Fetch a summary of recent orders for the morning briefing.

    Returns orders created in the last ``since_hours`` hours. Does not include
    PII; only operational fields (order_id, status, created_at, has_shipment).

    Args:
        ctx: Runtime context containing AgentDeps and the async database session.
        since_hours: Look-back window in hours. Default 24 (yesterday's orders).
        limit: Maximum number of orders to return.

    Returns:
        A list of OrderSummary objects ordered by creation time descending.

    Concurrency note:
        DB query is guarded with ctx.deps.db_lock because PydanticAI may run
        tools concurrently on the same AsyncSession.
    """
    from app.models.tables import Order, Shipment

    db = ctx.deps.db
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=since_hours)

    stmt = (
        select(Order)
        .where(Order.created_at >= since)
        .order_by(Order.created_at.desc())
        .limit(limit)
    )

    async with ctx.deps.db_lock:
        rows = (await db.execute(stmt)).scalars().all()

    result: list[OrderSummary] = []
    for order in rows:
        stmt_ship = select(Shipment).where(Shipment.order_id == order.id)
        async with ctx.deps.db_lock:
            shipment = await db.scalar(stmt_ship)
        result.append(
            OrderSummary(
                order_id=order.id,
                status=OrderStatus(order.status),
                created_at=order.created_at,
                has_shipment=shipment is not None,
            )
        )

    return result
