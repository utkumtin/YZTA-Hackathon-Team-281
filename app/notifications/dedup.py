"""app/notifications/dedup.py — notification_log üzerinden idempotency helper'ları.

Agent'a tool olarak sunulmaz; messaging tool'larının ve webhook callback
handler'ının içinden çağrılır. Bu ayrımı bilerek korumalı.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import NotificationLog


async def already_notified(
    db: AsyncSession,
    notif_type: str,
    entity_type: str,
    entity_ref: str,
    within_hours: int = 24,
) -> bool:
    """Son `within_hours` saat içinde aynı anahtar için bildirim gönderildi mi?

    Args:
        db: Async veritabanı session'ı.
        notif_type: Bildirim türü (örn. 'cargo_anomaly', 'low_stock').
        entity_type: Varlık türü ('order' veya 'sku').
        entity_ref: Varlık referansı (order_id string veya sku).
        within_hours: Kontrol penceresi (varsayılan 24 saat).

    Returns:
        True ise bildirim zaten gönderilmiş — tekrar gönderme.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=within_hours)
    stmt = (
        select(NotificationLog.id)
        .where(
            NotificationLog.notif_type == notif_type,
            NotificationLog.entity_type == entity_type,
            NotificationLog.entity_ref == entity_ref,
            NotificationLog.sent_at >= cutoff,
        )
        .limit(1)
    )
    row = (await db.execute(stmt)).first()
    return row is not None


async def record_notification(
    db: AsyncSession,
    notif_type: str,
    entity_type: str,
    entity_ref: str,
    channel: str,
    payload: dict | None = None,
) -> None:
    """Gönderim sonrası notification_log'a audit kaydı ekler.

    flush yapar, commit etmez — caller commit sorumluluğunu taşır.
    Bu sayede bir agent run'ı içindeki tüm insert'ler tek commit'te atılır;
    Telegram fail olursa rollback ile log tutarsızlığı önlenir.

    Args:
        db: Async veritabanı session'ı.
        notif_type: Bildirim türü.
        entity_type: Varlık türü.
        entity_ref: Varlık referansı.
        channel: Kanal ('tg_customer', 'tg_owner', 'email').
        payload: Ek bilgi (opsiyonel JSONB).
    """
    db.add(
        NotificationLog(
            notif_type=notif_type,
            entity_type=entity_type,
            entity_ref=entity_ref,
            channel=channel,
            payload=payload,
        )
    )
    await db.flush()
