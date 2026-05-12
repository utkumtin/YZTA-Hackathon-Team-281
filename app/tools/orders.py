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
    Kullanıcının belirli bir siparişi (order_id) hakkında detaylı bilgi getirir.
    
    Bu tool, müşterinin "Siparişim ne durumda?", "123 numaralı siparişim onaylandı mı?" 
    gibi sorularına yanıt vermek için kullanılır.

    Not: Bu fonksiyon KVKK gereği Müşteri Adı, Telefonu, Adresi vb. PII verilerini İÇERMEZ. 
    Kullanıcıya sipariş durumu iletilirken bu alanlar sadece order_id ve referans id'ler üzerinden ifade edilir.

    Args:
        ctx: AgentDeps runtime context'ini içerir.
        order_id: Sorgulanmak istenen siparişin eşsiz numarası (ID).

    Returns:
        Sipariş bulunursa OrderInfo döner, bulunamazsa None döner.
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
    Belirli bir kargo takip numarası (tracking_id) için kargo durumu bilgisini getirir.
    
    Kullanıcı "Kargom nerede?", "TRK123 takip numaralı kargo ne zaman teslim edilecek?" 
    gibi sorular sorduğunda kargonun anlık durumunu öğrenmek için kullanılır.
    Kargo hareketleri ve teslimat zamanı (ETA) gibi güncel durumları döner.

    Not: Bu veri PII barındırmaz, kargo sadece taşıyıcı, anlık şube ve statü bilgisi ile ifade edilir.

    Args:
        ctx: AgentDeps runtime context'ini içerir.
        tracking_id: Kargo firması tarafından verilen takip numarası.

    Returns:
        Kargo bulunursa ShipmentInfo döner, bulunamazsa None döner.
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
