"""app/api/webhook.py — Telegram webhook endpoint'i.

Akış:
    POST /telegram/webhook
    → verify_telegram_secret
    → Update.de_json
    → message → _handle_message  (redact → CSAgent → restore → send)
    → callback_query → _handle_callback_query  (HITL approve/reject)
    → {"ok": True}  ← her koşulda

Kritik: Telegram hata alırsa aynı update'i tekrar gönderir. Bu yüzden
endpoint exception'ı dışa sızdırmamalı; her zaman 200 + {"ok": True} dönmeli.
"""

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot, Update
from telegram.error import TelegramError

from app.agents.customer_support import get_customer_support_agent
from app.agents.deps import AgentDeps
from app.config import settings
from app.db import AsyncSessionLocal
from app.models.tables import NotificationLog, OutgoingEmail
from app.security.pii import redact, restore
from app.tools.messaging import _get_bot

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhook"])


# ── DB dependency ─────────────────────────────────────────────────────────────


async def _get_db() -> AsyncSession:
    async with AsyncSessionLocal() as db:
        yield db


# ── Telegram secret doğrulama ─────────────────────────────────────────────────


async def verify_telegram_secret(
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> None:
    """X-Telegram-Bot-Api-Secret-Token header'ını doğrular.

    Secret boşsa (geliştirme ortamı) kontrolü atlar.
    """
    if not settings.telegram_webhook_secret:
        return
    if x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status_code=403, detail="Invalid webhook secret")


# ── Endpoint ──────────────────────────────────────────────────────────────────


@router.post(
    "/telegram/webhook",
    dependencies=[Depends(verify_telegram_secret)],
    include_in_schema=False,
)
async def telegram_webhook(
    request: Request,
    db: AsyncSession = Depends(_get_db),
) -> dict:
    """Telegram'dan gelen update'leri işler.

    Her koşulda {"ok": True} döner. Telegram hata alırsa update'i
    tekrar gönderir ve sonsuz döngü oluşur.
    """
    try:
        data = await request.json()
        bot = _get_bot(settings.telegram_bot_token)
        update = Update.de_json(data, bot)

        if update.message and update.message.text:
            await _handle_message(update, db)
        elif update.callback_query:
            await _handle_callback_query(update, db)

    except Exception:
        logger.exception("webhook_unhandled_error")

    return {"ok": True}


# ── Message handler (reaktif akış) ──────────────────────────────────────


async def _handle_message(update: Update, db: AsyncSession) -> None:
    """Müşteri mesajını PII katmanından geçirip CSAgent'a yönlendirir."""

    message = update.message
    chat_id: int = message.chat_id
    raw_text: str = message.text or ""

    logger.info(
        "webhook_received",
        extra={"chat_id": chat_id, "raw_text": raw_text},
    )

    # 1. PII redaction
    redacted_text, pii_map = redact(raw_text)
    logger.info(
        "pii_scan",
        extra={
            "matches": list(pii_map.entries.keys()),
            "redacted_text": redacted_text,
        },
    )

    logger.info("router", extra={"target": "customer_support"})

    bot = _get_bot(settings.telegram_bot_token)

    try:
        async with AsyncSessionLocal() as agent_db:
            deps = AgentDeps(
                db=agent_db,
                owner_chat_id=settings.owner_telegram_id,
                bot_token=settings.telegram_bot_token,
            )

            agent = get_customer_support_agent()
            result = await agent.run(redacted_text, deps=deps)
            reply_redacted: str = result.output

        logger.info(
            "agent_response",
            extra={"chat_id": chat_id, "output_length": len(reply_redacted)},
        )

        # 2. PII restore — cevap agent'tan çıkınca map ile geri koy
        reply = restore(reply_redacted, pii_map)

        await bot.send_message(chat_id=chat_id, text=reply)

        logger.info("response_sent", extra={"chat_id": chat_id})

    except TelegramError as exc:
        logger.error(
            "telegram_send_failed",
            extra={"chat_id": chat_id, "error": str(exc)},
        )
    except Exception:
        logger.exception("agent_run_failed", extra={"chat_id": chat_id})
        try:
            await bot.send_message(
                chat_id=chat_id,
                text="Şu an sistemde bir gecikme var, bir dakika sonra tekrar dener misiniz?",
            )
        except TelegramError:
            pass


# ── Callback handler (HITL approve/reject) ───────────────────────────────


async def _handle_callback_query(update: Update, db: AsyncSession) -> None:
    """KOBİ inline keyboard callback'lerini işler.

    Desteklenen callback_data formatları:
        supplier_email:approve:{sku}
        supplier_email:reject:{sku}
    """

    cq = update.callback_query
    callback_data: str = cq.data or ""

    logger.info("callback_query_received", extra={"data": callback_data})

    parts = callback_data.split(":")
    bot = _get_bot(settings.telegram_bot_token)

    if len(parts) == 3 and parts[0] == "supplier_email":
        action = parts[1]  # "approve" | "reject"
        sku = parts[2]

        if action == "approve":
            await _approve_supplier_email(cq, sku, db, bot)
        elif action == "reject":
            await _reject_supplier_email(cq, sku, bot)
        elif action == "edit":
            await _edit_supplier_email(cq, sku, bot)
        else:
            await cq.answer("Bilinmeyen işlem.")
    else:
        # Tanınmayan callback — yine de answer() ile kapat
        await cq.answer()
        logger.warning("callback_query_unknown", extra={"data": callback_data})


async def _approve_supplier_email(cq, sku: str, db: AsyncSession, bot: Bot) -> None:
    """KOBİ 'Onayla' butonuna bastığında çalışır.

    notification_log'daki son low_stock payload'ından e-posta bilgilerini
    alır ve outgoing_emails tablosuna sent_mock kaydı ekler.
    """
    # notification_log'dan son low_stock kaydını bul
    stmt = (
        select(NotificationLog)
        .where(
            NotificationLog.notif_type == "low_stock",
            NotificationLog.entity_type == "sku",
            NotificationLog.entity_ref == sku,
            NotificationLog.channel == "tg_owner",
        )
        .order_by(NotificationLog.sent_at.desc())
        .limit(1)
    )
    log_row = await db.scalar(stmt)

    if log_row and log_row.payload:
        payload = log_row.payload
        to_email = payload.get("to_email", "")
        subject = payload.get("subject", f"{sku} - Stok Yenileme Talebi")
        body = payload.get("body", "")
    else:
        to_email = ""
        subject = f"{sku} - Stok Yenileme Talebi"
        body = ""
        logger.warning(
            "approve_notification_log_missing",
            extra={"sku": sku},
        )

    db.add(
        OutgoingEmail(
            to_email=to_email,
            subject=subject,
            body=body,
            related_sku=sku,
            status="sent_mock",
        )
    )
    await db.commit()

    logger.info("supplier_email_approved", extra={"sku": sku, "to_email": to_email})

    await cq.answer("✅ Mail tedarikçiye gönderildi (mock).")

    try:
        await bot.send_message(
            chat_id=cq.from_user.id,
            text=f"✅ {sku} için tedarikçi maili gönderildi (mock).",
        )
    except TelegramError:
        pass


async def _reject_supplier_email(cq, sku: str, bot: Bot) -> None:
    """KOBİ 'Reddet' butonuna bastığında çalışır.

    outgoing_emails'e kayıt eklenmez. Log'a email_rejected_by_owner yazılır.
    """
    logger.info("email_rejected_by_owner", extra={"sku": sku})

    await cq.answer("❌ Anlaşıldı, iptal edildi.")

    try:
        await bot.send_message(
            chat_id=cq.from_user.id,
            text=f"❌ {sku} için tedarikçi mail taslağı iptal edildi.",
        )
    except TelegramError:
        pass


async def _edit_supplier_email(cq, sku: str, bot: Bot) -> None:
    """KOBİ 'Düzenle' butonuna bastığında çalışır.

    Düzenleme özelliği ileride aktif olacak. KOBİ bilgilendirilir,
    orijinal mesaj ve butonlar değiştirilmez.
    """
    logger.info("supplier_email_edit_requested", extra={"sku": sku})

    await cq.answer("ℹ️ Düzenleme özelliği ileride aktif olacak.")

    try:
        await bot.send_message(
            chat_id=cq.from_user.id,
            text=(
                f"ℹ️ {sku} için taslak düzenleme özelliği ileride aktif olacak.\n"
                "Şimdilik Onayla veya Reddet seçeneğini kullanabilirsiniz."
            ),
        )
    except TelegramError:
        pass
