"""
tests/smoke/test_briefing.py — Sabah Brifingi entegrasyon testleri

Notlar:
  - trigger-briefing endpoint'i MorningBriefingAgent'ı çalıştırır (LLM gerektirir).
    LLM olmayan CI/test ortamı için agent.run çağrısı mock'lanır; HTTP katmanı,
    DB işlemleri ve endpoint yönlendirmesi gerçek kod üzerinden çalışır.
  - list_orders_summary ve list_active_shipments testleri doğrudan tool imzasını
    doğrular; LLM gerektirmez.
"""

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import AsyncSessionLocal
from app.main import app
from app.models.domain import (
    ActiveShipmentInfo,
    BriefingSummary,
    MessageDispatchResult,
    OrderStatus,
    OrderSummary,
    ShipmentStatus,
)

# ── Yardımcı: uygulama DB üzerinde sorgu çalıştır ────────────────────────────


async def _query_scalar(stmt):
    async with AsyncSessionLocal() as db:
        return await db.scalar(stmt)


# ── Fixture: reset + HTTP client ──────────────────────────────────────────────


@pytest.fixture
async def reset_client():
    """
    Her test için temiz AsyncClient döndürür.
    Lifespan devre dışı bırakılır; sadece router mantığı test edilir.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ══════════════════════════════════════════════════════════════════════════════
# POST /demo/trigger-briefing endpoint testleri
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_trigger_briefing_returns_200(reset_client: AsyncClient):
    """/demo/trigger-briefing LLM mock ile HTTP 200 döndürmeli."""
    mock_summary = BriefingSummary(
        briefing_date=date.today(),
        order_count=2,
        active_shipment_count=1,
        delayed_shipment_count=0,
        low_stock_count=1,
        message_sent=True,
    )

    with patch(
        "app.agents.proactive_jobs.run_morning_briefing",
        new=AsyncMock(return_value=mock_summary),
    ):
        await reset_client.post("/demo/reset")
        response = await reset_client.post("/demo/trigger-briefing")

    assert response.status_code == 200, f"Beklenen 200, alınan {response.status_code}"


@pytest.mark.asyncio
async def test_trigger_briefing_response_schema(reset_client: AsyncClient):
    """/demo/trigger-briefing yanıtı BriefingSummary alanlarını içermeli."""
    mock_summary = BriefingSummary(
        briefing_date=date.today(),
        order_count=5,
        active_shipment_count=3,
        delayed_shipment_count=1,
        low_stock_count=2,
        message_sent=True,
    )

    with patch(
        "app.agents.proactive_jobs.run_morning_briefing",
        new=AsyncMock(return_value=mock_summary),
    ):
        await reset_client.post("/demo/reset")
        response = await reset_client.post("/demo/trigger-briefing")

    assert response.status_code == 200
    body = response.json()

    expected_fields = [
        "briefing_date",
        "order_count",
        "active_shipment_count",
        "delayed_shipment_count",
        "low_stock_count",
        "message_sent",
    ]
    for field in expected_fields:
        assert field in body, f"'{field}' trigger-briefing yanıtında olmalı"

    assert body["order_count"] == 5
    assert body["delayed_shipment_count"] == 1
    assert body["message_sent"] is True


@pytest.mark.asyncio
async def test_trigger_briefing_after_reset_returns_correct_metrics(
    reset_client: AsyncClient,
):
    """
    reset → trigger-briefing akışı: fixture'daki sipariş sayısı ile
    mock summary'nin order_count'u uyuştuğunda test geçer.

    Bu test HTTP → demo endpoint → mock agent zincirini doğrular.
    """
    mock_summary = BriefingSummary(
        briefing_date=date.today(),
        order_count=2,  # fixtures'da 2 sipariş var
        active_shipment_count=1,
        delayed_shipment_count=0,
        low_stock_count=1,
        message_sent=True,
    )

    with patch(
        "app.agents.proactive_jobs.run_morning_briefing",
        new=AsyncMock(return_value=mock_summary),
    ):
        r_reset = await reset_client.post("/demo/reset")
        assert r_reset.status_code == 200, "reset başarısız"

        r_briefing = await reset_client.post("/demo/trigger-briefing")
        assert r_briefing.status_code == 200, "trigger-briefing başarısız"

    body = r_briefing.json()
    assert body["order_count"] == 2
    assert body["message_sent"] is True


@pytest.mark.asyncio
async def test_trigger_briefing_when_demo_disabled_returns_403(
    reset_client: AsyncClient,
):
    """/demo/trigger-briefing, demo mode kapalıyken HTTP 403 döndürmeli."""
    with patch("app.api.demo.settings") as mock_settings:
        mock_settings.demo_mode_enabled = False
        response = await reset_client.post("/demo/trigger-briefing")

    assert response.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# list_orders_summary tool testleri (doğrudan tool çağrısı, DB gerektirir)
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_orders_summary_returns_recent_orders():
    """
    list_orders_summary, reset sonrası DB'deki fixture siparişlerini döndürmeli.

    Fixture'da 2 sipariş var; ikisi de son 24 saat içinde oluşturulmuş.
    Tool'un DB'yi doğru okuduğunu doğrular.
    """

    from app.agents.deps import AgentDeps
    from app.tools.orders import list_orders_summary

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/demo/reset")

    async with AsyncSessionLocal() as db:
        deps = AgentDeps(db=db)
        ctx = MagicMock()
        ctx.deps = deps

        orders = await list_orders_summary(ctx, since_hours=48)

    assert len(orders) >= 2, f"En az 2 sipariş bekleniyor, {len(orders)} döndü"
    for order in orders:
        assert isinstance(order, OrderSummary)
        assert order.order_id > 0
        assert isinstance(order.status, OrderStatus)


@pytest.mark.asyncio
async def test_list_orders_summary_excludes_old_orders():
    """
    list_orders_summary, since_hours penceresinin dışındaki siparişleri dışarıda bırakmalı.

    since_hours=0 ile çağrıldığında yakın zamanda oluşturulan kayıtlar dışında
    sonuç dönmemeli.
    """
    from app.agents.deps import AgentDeps
    from app.tools.orders import list_orders_summary

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/demo/reset")

    async with AsyncSessionLocal() as db:
        deps = AgentDeps(db=db)
        ctx = MagicMock()
        ctx.deps = deps

        # since_hours=0 → şu andan önce oluşturulan hiçbir sipariş pencereye girmez
        orders = await list_orders_summary(ctx, since_hours=0)

    assert len(orders) == 0, "since_hours=0 ile sipariş gelmemeli"


# ══════════════════════════════════════════════════════════════════════════════
# list_active_shipments tool testleri
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_list_active_shipments_returns_non_delivered():
    """
    list_active_shipments, delivered ve returned olmayan kargoları döndürmeli.

    Fixture'da 1 in_transit + 1 delivered var; sadece in_transit olanı döndürmeli.
    """
    from app.agents.deps import AgentDeps
    from app.tools.shipments import list_active_shipments

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/demo/reset")

    async with AsyncSessionLocal() as db:
        deps = AgentDeps(db=db)
        ctx = MagicMock()
        ctx.deps = deps

        shipments = await list_active_shipments(ctx)

    assert len(shipments) >= 1, "En az 1 aktif kargo bekleniyor"
    for s in shipments:
        assert isinstance(s, ActiveShipmentInfo)
        assert s.status not in (ShipmentStatus.DELIVERED, ShipmentStatus.RETURNED), (
            f"Teslim edilmiş/iade edilmiş kargo aktif listede olmamalı: {s.tracking_id}"
        )


@pytest.mark.asyncio
async def test_list_active_shipments_flags_delayed():
    """
    list_active_shipments, 24 saatten eski son güncellemeye sahip kargoları
    is_delayed=True ile işaretlemeli.
    """
    from app.agents.deps import AgentDeps
    from app.tools.shipments import list_active_shipments

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/demo/reset")
        # Shipment 1'i 30 saat eski yaparak gecikme bayrağı tetiklenir
        await client.post(
            "/demo/set-anomaly",
            json={"shipment_id": 1, "hours_old": 30},
        )

    async with AsyncSessionLocal() as db:
        deps = AgentDeps(db=db)
        ctx = MagicMock()
        ctx.deps = deps

        shipments = await list_active_shipments(ctx)

    delayed = [s for s in shipments if s.is_delayed]
    assert len(delayed) >= 1, "30 saat eski kargo is_delayed=True ile dönmeli"


# ══════════════════════════════════════════════════════════════════════════════
# send_morning_briefing tool testleri
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_send_morning_briefing_returns_sent_status():
    """
    send_morning_briefing, Telegram gönderimi mock'landığında status='sent' döndürmeli.

    Gerçek bir Telegram token'ı olmadan da tool'un doğru result ürettiğini doğrular.
    """
    from app.agents.deps import AgentDeps
    from app.tools.messaging import send_morning_briefing

    async with AsyncSessionLocal() as db:
        deps = AgentDeps(
            db=db,
            owner_chat_id=None,  # None ise _send_telegram_message erken döner
            bot_token=None,
        )
        ctx = MagicMock()
        ctx.deps = deps

        result = await send_morning_briefing(
            ctx,
            briefing_date=date.today(),
            order_count=3,
            active_shipment_count=2,
            delayed_shipment_count=1,
            low_stock_count=0,
        )

    assert isinstance(result, MessageDispatchResult)
    assert result.status == "sent"
    assert result.channel == "tg_owner"
    assert result.entity_ref == "briefing"


@pytest.mark.asyncio
async def test_send_morning_briefing_message_contains_metrics():
    """
    send_morning_briefing'in oluşturduğu mesaj metin, en az 3 metrik içermeli.

    Tool'un Telegram'a gönderdiği mesajı yakalamak için _send_telegram_message mock'lanır.
    """
    from app.agents.deps import AgentDeps
    from app.tools.messaging import send_morning_briefing

    captured_text: list[str] = []

    async def _fake_send(bot_token, chat_id, text, reply_markup=None):
        captured_text.append(text)

    async with AsyncSessionLocal() as db:
        deps = AgentDeps(db=db, owner_chat_id=12345, bot_token="fake-token")
        ctx = MagicMock()
        ctx.deps = deps

        with patch(
            "app.tools.messaging._send_telegram_message",
            side_effect=_fake_send,
        ):
            await send_morning_briefing(
                ctx,
                briefing_date=date(2026, 5, 13),
                order_count=12,
                active_shipment_count=8,
                delayed_shipment_count=3,
                low_stock_count=1,
            )

    assert len(captured_text) == 1, "Tam olarak 1 mesaj gönderilmeli"
    msg = captured_text[0]

    assert "Günaydın" in msg, "Mesaj 'Günaydın' ile başlamalı"
    assert "12" in msg, "Sipariş sayısı mesajda görünmeli"
    assert "8" in msg, "Aktif kargo sayısı mesajda görünmeli"
    assert "3" in msg, "Geciken kargo sayısı mesajda görünmeli"
    assert "1" in msg, "Düşük stok sayısı mesajda görünmeli"
