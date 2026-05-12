"""Telegram mesajlaşma ve owner approval tool'ları."""

from datetime import datetime, timedelta, timezone

from pydantic_ai import RunContext
from sqlalchemy import select
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Forbidden, TelegramError

from app.agents.deps import AgentDeps
from app.models.domain import LowStockItem, MessageDispatchResult, SupplierEmailDraft
from app.models.tables import Customer, NotificationLog, Order


async def _send_telegram_message(
    bot_token: str | None,
    chat_id: int | None,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    """Small async wrapper around python-telegram-bot.

    Demo ortamında bot token veya chat id yoksa tool akışını kırmaz.
    Böylece DB/log/idempotency testleri Telegram olmadan da çalışabilir.
    """

    if not bot_token or not chat_id:
        return

    bot = Bot(token=bot_token)
    await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)


async def send_proactive_message(
    ctx: RunContext[AgentDeps],
    order_id: int,
    message: str,
) -> MessageDispatchResult:
    """
    Send a proactive Telegram message to the customer of an order.

    This tool is idempotent for 24 hours. Before sending, it checks
    ``notification_log`` for a previous ``cargo_anomaly`` notification with the
    same order id and ``tg_customer`` channel. If such a record exists within
    the last 24 hours, the Telegram message is not sent and the tool returns
    ``skipped_duplicate``.

    Args:
        ctx: Runtime context containing AgentDeps, db session, bot token and owner id.
        order_id: Order id whose customer should receive the proactive message.
        message: Customer-facing message text.

    Returns:
        MessageDispatchResult with status ``sent``, ``skipped_duplicate``,
        ``skipped_no_chat_id`` or ``skipped_blocked``.

    Concurrency note:
        PydanticAI may execute multiple tools concurrently. SQLAlchemy AsyncSession
        does not allow concurrent operations on the same session, so DB reads/writes
        are guarded with ctx.deps.db_lock. Telegram I/O is intentionally outside the
        DB lock.
    """

    db = ctx.deps.db
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)
    entity_ref = str(order_id)

    duplicate_stmt = select(NotificationLog).where(
        NotificationLog.notif_type == "cargo_anomaly",
        NotificationLog.entity_type == "order",
        NotificationLog.entity_ref == entity_ref,
        NotificationLog.channel == "tg_customer",
        NotificationLog.sent_at >= since,
    )

    order_stmt = (
        select(Order, Customer)
        .join(Customer, Customer.id == Order.customer_id)
        .where(Order.id == order_id)
    )

    async with ctx.deps.db_lock:
        duplicate = await db.scalar(duplicate_stmt)

        if duplicate:
            return MessageDispatchResult(
                status="skipped_duplicate",
                channel="tg_customer",
                entity_ref=entity_ref,
                detail="A proactive customer message for this order was already sent within 24 hours.",
            )

        row = (await db.execute(order_stmt)).first()

    if not row:
        return MessageDispatchResult(
            status="skipped_no_chat_id",
            channel="tg_customer",
            entity_ref=entity_ref,
            detail="Order not found.",
        )

    _order, customer = row

    if not customer.telegram_chat_id:
        return MessageDispatchResult(
            status="skipped_no_chat_id",
            channel="tg_customer",
            entity_ref=entity_ref,
            detail="Customer has no Telegram chat id.",
        )

    try:
        await _send_telegram_message(
            bot_token=ctx.deps.bot_token,
            chat_id=customer.telegram_chat_id,
            text=message,
        )
    except Forbidden:
        return MessageDispatchResult(
            status="skipped_blocked",
            channel="tg_customer",
            entity_ref=entity_ref,
            detail="Customer blocked the bot.",
        )
    except TelegramError as exc:
        return MessageDispatchResult(
            status="skipped_blocked",
            channel="tg_customer",
            entity_ref=entity_ref,
            detail=f"Telegram error: {exc}",
        )

    async with ctx.deps.db_lock:
        # Telegram gönderimi sırasında başka paralel tool aynı notification'ı
        # yazmış olabilir; commit öncesi duplicate kontrolünü tekrar yap.
        duplicate_after_send = await db.scalar(duplicate_stmt)

        if duplicate_after_send:
            return MessageDispatchResult(
                status="skipped_duplicate",
                channel="tg_customer",
                entity_ref=entity_ref,
                detail="A proactive customer message for this order was already sent within 24 hours.",
            )

        db.add(
            NotificationLog(
                notif_type="cargo_anomaly",
                entity_type="order",
                entity_ref=entity_ref,
                channel="tg_customer",
                sent_at=now,
                payload={"message": message},
            )
        )
        await db.commit()

    return MessageDispatchResult(
        status="sent",
        channel="tg_customer",
        entity_ref=entity_ref,
        detail="Proactive customer message sent.",
    )


async def send_owner_summary(
    ctx: RunContext[AgentDeps],
    items: list[LowStockItem],
) -> MessageDispatchResult:
    """
    Send a deterministic low-stock summary to the owner via Telegram.

    This tool does not use an LLM. It renders a static template from the given
    low-stock items and sends it to OWNER_TELEGRAM_ID from runtime settings.

    Args:
        ctx: Runtime context containing AgentDeps, owner chat id and bot token.
        items: Low stock items to include in the owner summary.

    Returns:
        MessageDispatchResult. If items is empty, returns ``skipped_no_anomaly``.
    """

    if not items:
        return MessageDispatchResult(
            status="skipped_no_anomaly",
            channel="tg_owner",
            entity_ref="low_stock",
            detail="No low-stock items detected.",
        )

    lines = ["⚠️ Düşük Stok Özeti", "", "Eşik altında kalan ürünler:"]
    for item in items:
        lines.append(
            f"- {item.sku} | {item.name}: {item.current_qty}/{item.threshold} "
            f"| Tedarikçi: {item.supplier_name}"
        )

    text = "\n".join(lines)

    await _send_telegram_message(
        bot_token=ctx.deps.bot_token,
        chat_id=ctx.deps.owner_chat_id,
        text=text,
    )

    return MessageDispatchResult(
        status="sent",
        channel="tg_owner",
        entity_ref="low_stock",
        detail=f"Owner low-stock summary sent for {len(items)} item(s).",
    )


async def send_owner_email_draft(
    ctx: RunContext[AgentDeps],
    sku: str,
    draft: SupplierEmailDraft,
) -> MessageDispatchResult:
    """
    Send a supplier email draft to the owner with Approve/Reject buttons.

    The Telegram inline keyboard callback data contains the SKU so the webhook
    callback handler can later identify which draft is being approved or rejected.

    Args:
        ctx: Runtime context containing AgentDeps, owner chat id and bot token.
        sku: Product SKU related to the supplier email draft.
        draft: Structured supplier email draft.

    Returns:
        MessageDispatchResult with channel ``tg_owner`` and entity_ref equal to SKU.

    Concurrency note:
        Telegram I/O is outside the DB lock. Only the notification_log write/commit
        is guarded with ctx.deps.db_lock.
    """

    text = (
        "📩 Tedarikçi E-posta Taslağı\n\n"
        f"SKU: {sku}\n"
        f"To: {draft.to_email}\n"
        f"Subject: {draft.subject}\n\n"
        f"{draft.body}\n\n"
        "Bu taslak gönderilsin mi?"
    )

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Onayla", callback_data=f"supplier_email:approve:{sku}"),
                InlineKeyboardButton(
                    "❌ Reddet", callback_data=f"supplier_email:reject:{sku}"),
            ]
        ]
    )

    await _send_telegram_message(
        bot_token=ctx.deps.bot_token,
        chat_id=ctx.deps.owner_chat_id,
        text=text,
        reply_markup=keyboard,
    )

    db = ctx.deps.db

    async with ctx.deps.db_lock:
        db.add(
            NotificationLog(
                notif_type="low_stock",
                entity_type="sku",
                entity_ref=sku,
                channel="tg_owner",
                sent_at=datetime.now(timezone.utc),
                payload={
                    "to_email": draft.to_email,
                    "subject": draft.subject,
                    "body": draft.body,
                    "suggested_qty": draft.suggested_qty,
                },
            )
        )
        await db.commit()

    return MessageDispatchResult(
        status="sent",
        channel="tg_owner",
        entity_ref=sku,
        detail="Supplier email draft sent to owner for approval.",
    )
