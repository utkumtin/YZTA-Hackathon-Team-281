"""
tests/smoke/test_integration.py — entegrasyon testi

POST /demo/reset → POST /demo/set-anomaly → POST /demo/trigger-jobs
akışını gerçek DB ve FastAPI test client'ı ile doğrular.

Notlar:
  - trigger-jobs endpoint'i ProactiveJobsAgent'ı çalıştırır (LLM gerektirir).
    LLM olmayan CI/test ortamı için agent.run çağrısı mock'lanır; HTTP katmanı,
    DB işlemleri ve endpoint yönlendirmesi gerçek kod üzerinden çalışır.
  - reset ve set-anomaly testleri LLM gerektirmez; her zaman çalışır.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.main import app
from app.models.domain import ProactiveRunSummary
from app.models.tables import NotificationLog, Shipment

# ── Yardımcı: uygulama DB üzerinde sorgu çalıştır ────────────────────────────


async def _query_scalar(stmt):
    async with AsyncSessionLocal() as db:
        return await db.scalar(stmt)


async def _query_all(stmt):
    async with AsyncSessionLocal() as db:
        result = await db.execute(stmt)
        return result.all()


# ── Fixture: her test öncesi /demo/reset çağrısı ─────────────────────────────


@pytest.fixture
async def reset_client():
    """
    Her test için temiz bir AsyncClient döndürür.
    Fixture, lifespan'i devre dışı bırakarak sadece router mantığını test eder;
    bu sayede Telegram token veya DB bağlantı hatası testi engellemez.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


# ══════════════════════════════════════════════════════════════════════════════
# POST /demo/reset testleri
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_reset_returns_200(reset_client: AsyncClient):
    """/demo/reset HTTP 200 dönmeli."""
    response = await reset_client.post("/demo/reset")
    assert response.status_code == 200, f"Beklenen 200, alınan {response.status_code}"


@pytest.mark.asyncio
async def test_reset_response_body_structure(reset_client: AsyncClient):
    """/demo/reset yanıt gövdesi beklenen alanları içermeli."""
    response = await reset_client.post("/demo/reset")
    body = response.json()

    assert body["status"] == "ok"
    assert "inserted" in body
    inserted = body["inserted"]
    for key in ("customers", "suppliers", "products", "stock", "orders", "shipments"):
        assert key in inserted, f"'{key}' inserted alanında olmalı"
        assert inserted[key] > 0, f"'{key}' sayısı sıfırdan büyük olmalı"


@pytest.mark.asyncio
async def test_reset_seeds_shipment_to_db(reset_client: AsyncClient):
    """/demo/reset sonrası DB'de en az 1 shipment kaydı olmalı."""
    await reset_client.post("/demo/reset")

    count = await _query_scalar(select(Shipment).limit(1))
    assert count is not None, "reset sonrası DB'de shipment kaydı bekleniyor"


@pytest.mark.asyncio
async def test_reset_clears_notification_log(reset_client: AsyncClient):
    """/demo/reset notification_log tablosunu temizlemeli."""
    await reset_client.post("/demo/reset")

    count_stmt = select(NotificationLog)
    rows = await _query_all(count_stmt)
    assert len(rows) == 0, "reset sonrası notification_log boş olmalı"


@pytest.mark.asyncio
async def test_reset_is_idempotent(reset_client: AsyncClient):
    """Arka arkaya iki /demo/reset çağrısı da HTTP 200 dönmeli."""
    r1 = await reset_client.post("/demo/reset")
    r2 = await reset_client.post("/demo/reset")
    assert r1.status_code == 200
    assert r2.status_code == 200


# ══════════════════════════════════════════════════════════════════════════════
# POST /demo/set-anomaly testleri
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_set_anomaly_returns_200(reset_client: AsyncClient):
    """/demo/set-anomaly geçerli shipment_id ile HTTP 200 dönmeli."""
    await reset_client.post("/demo/reset")

    response = await reset_client.post(
        "/demo/set-anomaly",
        json={"shipment_id": 1, "hours_old": 10},
    )
    assert response.status_code == 200, f"Beklenen 200, alınan {response.status_code}"


@pytest.mark.asyncio
async def test_set_anomaly_response_body(reset_client: AsyncClient):
    """/demo/set-anomaly yanıtı beklenen alanları içermeli."""
    await reset_client.post("/demo/reset")

    response = await reset_client.post(
        "/demo/set-anomaly",
        json={"shipment_id": 1, "hours_old": 12},
    )
    body = response.json()
    assert body["status"] == "ok"
    assert body["shipment_id"] == 1
    assert body["new_status"] == "in_transit"
    assert "last_status_change_at" in body


@pytest.mark.asyncio
async def test_set_anomaly_updates_db(reset_client: AsyncClient):
    """/demo/set-anomaly DB'deki shipment'ı in_transit ve eski timestamp ile günceller."""
    await reset_client.post("/demo/reset")

    hours_old = 14
    await reset_client.post(
        "/demo/set-anomaly",
        json={"shipment_id": 1, "hours_old": hours_old},
    )

    shipment = await _query_scalar(select(Shipment).where(Shipment.id == 1))
    assert shipment is not None
    assert shipment.status == "in_transit"

    now = datetime.now(timezone.utc)
    age_hours = (now - shipment.last_status_change_at).total_seconds() / 3600
    assert age_hours >= hours_old - 0.1, (
        f"last_status_change_at en az {hours_old} saat eski olmalı, fiilen: {age_hours:.1f} saat"
    )


@pytest.mark.asyncio
async def test_set_anomaly_nonexistent_shipment_returns_404(reset_client: AsyncClient):
    """/demo/set-anomaly olmayan shipment_id için HTTP 404 dönmeli."""
    await reset_client.post("/demo/reset")

    response = await reset_client.post(
        "/demo/set-anomaly",
        json={"shipment_id": 99999, "hours_old": 10},
    )
    assert response.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# POST /demo/reset → /demo/set-anomaly → /demo/trigger-jobs tam akış
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_full_flow_reset_set_anomaly_trigger_jobs(reset_client: AsyncClient):
    """
    Tam entegrasyon akışı:
      1. /demo/reset  → DB temiz + seed verisi yüklenir
      2. /demo/set-anomaly  → shipment anomali durumuna alınır
      3. /demo/trigger-jobs  → ProactiveJobsAgent çalışır (mock)

    LLM çağrısı mock'lanır; agent ProactiveRunSummary döndürür.
    Bu test HTTP yönlendirme, DB işlemleri ve agent entegrasyonunu doğrular.
    """
    mock_summary = ProactiveRunSummary(
        anomalies_detected=1,
        anomaly_messages_sent=1,
        anomalies_skipped_duplicate=0,
        anomalies_skipped_no_chat=0,
        low_stock_detected=1,
        low_stock_drafts_sent=1,
        low_stock_skipped_duplicate=0,
    )

    with patch(
        "app.agents.proactive_jobs.run_proactive_jobs",
        new=AsyncMock(return_value=mock_summary),
    ):
        r_reset = await reset_client.post("/demo/reset")
        assert r_reset.status_code == 200, "reset başarısız"

        r_anomaly = await reset_client.post(
            "/demo/set-anomaly",
            json={"shipment_id": 1, "hours_old": 10},
        )
        assert r_anomaly.status_code == 200, "set-anomaly başarısız"

        r_trigger = await reset_client.post("/demo/trigger-jobs")
        assert r_trigger.status_code == 200, "trigger-jobs başarısız"

    body = r_trigger.json()
    assert body["anomalies_detected"] == 1
    assert body["anomaly_messages_sent"] == 1
    assert body["low_stock_detected"] == 1
    assert body["low_stock_drafts_sent"] == 1


@pytest.mark.asyncio
async def test_trigger_jobs_returns_proactive_run_summary_schema(reset_client: AsyncClient):
    """/demo/trigger-jobs yanıtı ProactiveRunSummary alanlarını içermeli."""
    mock_summary = ProactiveRunSummary(
        anomalies_detected=0,
        anomaly_messages_sent=0,
        anomalies_skipped_duplicate=0,
        anomalies_skipped_no_chat=0,
        low_stock_detected=0,
        low_stock_drafts_sent=0,
        low_stock_skipped_duplicate=0,
    )

    with patch(
        "app.agents.proactive_jobs.run_proactive_jobs",
        new=AsyncMock(return_value=mock_summary),
    ):
        await reset_client.post("/demo/reset")
        response = await reset_client.post("/demo/trigger-jobs")

    assert response.status_code == 200
    body = response.json()

    expected_fields = [
        "anomalies_detected",
        "anomaly_messages_sent",
        "anomalies_skipped_duplicate",
        "anomalies_skipped_no_chat",
        "low_stock_detected",
        "low_stock_drafts_sent",
        "low_stock_skipped_duplicate",
    ]
    for field in expected_fields:
        assert field in body, f"'{field}' trigger-jobs yanıtında olmalı"


@pytest.mark.asyncio
async def test_set_anomaly_makes_shipment_detectable_by_list_shipments_anomaly(
    reset_client: AsyncClient,
):
    """
    /demo/set-anomaly sonrası DB'deki shipment, list_shipments_anomaly tool'u
    tarafından anomali olarak tespit edilebilmeli.

    Doğrulama: shipment.last_status_change_at değerinin tool'un
    older_than_hours=6 eşiğini geçtiğini doğrular.
    """
    await reset_client.post("/demo/reset")
    await reset_client.post(
        "/demo/set-anomaly",
        json={"shipment_id": 1, "hours_old": 10},
    )

    shipment = await _query_scalar(select(Shipment).where(Shipment.id == 1))
    assert shipment is not None
    assert shipment.status == "in_transit"

    now = datetime.now(timezone.utc)
    age_hours = (now - shipment.last_status_change_at).total_seconds() / 3600
    assert age_hours > 6, (
        f"Anomali tespiti için kargo 6 saatten eski olmalı; fiilen {age_hours:.1f} saat"
    )
