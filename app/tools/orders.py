from datetime import date, datetime, timedelta
from typing import Optional
from pydantic_ai import RunContext
from app.agents.deps import AgentDeps
from app.models.domain import (
    OrderInfo,
    ShipmentInfo,
    OrderStatus,
    ShipmentStatus,
    Carrier,
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
