"""
tests/smoke/test_tools.py — Tool sözleşme doğrulama smoke testleri

Kural: Bu testler gerçek PostgreSQL veritabanına bağlanır; mock yok.
      Çalıştırmadan önce Docker DB'nin ayakta olması gerekir.
      `pytest tests/smoke/test_tools.py`

Kapsam:
  - get_order: geçerli / geçersiz order_id
  - list_shipments_anomaly: anomali bulma (older_than_hours eşiği)
  - list_low_stock: eşik altı SKU tespiti
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine, async_sessionmaker, create_async_engine

from app.agents.deps import AgentDeps
from app.config import settings
from app.models.domain import OrderStatus
from app.models.tables import (
    Customer,
    Order,
    Product,
    Shipment,
    Stock,
    Supplier,
)
from app.tools.orders import get_order
from app.tools.shipments import list_shipments_anomaly
from app.tools.stock import list_low_stock

# Tüm testler tek event loop üzerinde çalışır; engine loop uyumsuzluğunu önler.
pytestmark = pytest.mark.asyncio(loop_scope="session")

# ── Sahte RunContext oluştur ─────────────────────────────────────────


def _make_ctx(db: AsyncSession) -> MagicMock:
    """AgentDeps içeren minimal bir RunContext mock'u döndürür."""
    deps = AgentDeps(db=db)
    ctx = MagicMock()
    ctx.deps = deps
    return ctx


# ── Her test için izole DB session + seed verisi ─────────────────────


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    """Session boyunca tek engine; loop uyumsuzluğunu önler."""
    engine: AsyncEngine = create_async_engine(settings.database_url, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine):
    """
    Her test için temiz bir transaction başlatır.
    Test bitince ROLLBACK yaparak seed verisini geri alır.
    Böylece testler birbirini etkilemez.
    """
    session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
        bind=db_engine,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    async with session_factory() as session:
        await session.begin()
        try:
            yield session
        finally:
            await session.rollback()


@pytest_asyncio.fixture
async def seeded_db(db_session: AsyncSession):
    """
    list_shipments_anomaly ve list_low_stock için gereken
    minimal veri setini seed eder; test bitince rollback ile temizlenir.
    """
    now = datetime.now(timezone.utc)

    supplier = Supplier(
        id=9001,
        name="Test Tedarikçi",
        email="test@tedarikci.example.com",
        phone="+901234567890",
    )
    db_session.add(supplier)

    product_normal = Product(
        sku="TEST-SKU-HIGH",
        name="Yüksek Stok Ürün",
        description="Stok eşiğin üstünde.",
        supplier_id=9001,
        price=Decimal("50.00"),
    )
    product_low = Product(
        sku="TEST-SKU-LOW",
        name="Düşük Stok Ürün",
        description="Stok eşiğin altında.",
        supplier_id=9001,
        price=Decimal("75.00"),
    )
    db_session.add_all([product_normal, product_low])

    stock_normal = Stock(sku="TEST-SKU-HIGH", current_qty=100, threshold=10)
    stock_low = Stock(sku="TEST-SKU-LOW", current_qty=3, threshold=10)
    db_session.add_all([stock_normal, stock_low])

    customer = Customer(
        id=9001,
        name="Test Müşteri",
        phone="+905559999999",
        email="test@musteri.example.com",
        telegram_chat_id=9999999991,
    )
    db_session.add(customer)

    order_normal = Order(
        id=9001,
        customer_id=9001,
        status="shipped",
        total=Decimal("200.00"),
        created_at=now - timedelta(days=1),
        updated_at=now - timedelta(hours=1),
    )
    order_anomaly = Order(
        id=9002,
        customer_id=9001,
        status="shipped",
        total=Decimal("350.00"),
        created_at=now - timedelta(days=2),
        updated_at=now - timedelta(hours=20),
    )
    db_session.add_all([order_normal, order_anomaly])

    shipment_normal = Shipment(
        id=9001,
        order_id=9001,
        tracking_id="TEST-TRK-NORMAL",
        carrier="Aras",
        status="in_transit",
        current_branch="Ankara Merkez",
        last_status_change_at=now - timedelta(hours=2),
        eta=date.today() + timedelta(days=1),
    )
    shipment_anomaly = Shipment(
        id=9002,
        order_id=9002,
        tracking_id="TEST-TRK-ANOMALY",
        carrier="MNG",
        status="in_transit",
        current_branch="İzmir Şube",
        last_status_change_at=now - timedelta(hours=10),
        eta=date.today(),
    )
    db_session.add_all([shipment_normal, shipment_anomaly])

    await db_session.flush()
    yield db_session


# get_order testleri


@pytest.mark.asyncio
async def test_get_order_valid_id_returns_order_info(db_session: AsyncSession):
    """Geçerli bir order_id verildiğinde get_order OrderInfo dönmelidir."""
    ctx = _make_ctx(db_session)

    result = await get_order(ctx, order_id=1)

    assert result is not None, "Geçerli ID için None dönmemeli"
    assert result.order_id == 1
    assert result.status in OrderStatus.__members__.values() or result.status in list(OrderStatus)
    assert result.has_shipment is True or result.has_shipment is False
    assert result.customer_id is not None


@pytest.mark.asyncio
async def test_get_order_invalid_id_returns_none(db_session: AsyncSession):
    """Geçersiz (≤ 0) order_id verildiğinde get_order None dönmelidir."""
    ctx = _make_ctx(db_session)

    result = await get_order(ctx, order_id=0)

    assert result is None, "Geçersiz ID (0) için None bekleniyor"


@pytest.mark.asyncio
async def test_get_order_negative_id_returns_none(db_session: AsyncSession):
    """Negatif order_id verildiğinde get_order None dönmelidir."""
    ctx = _make_ctx(db_session)

    result = await get_order(ctx, order_id=-42)

    assert result is None, "Negatif ID için None bekleniyor"


@pytest.mark.asyncio
async def test_get_order_result_has_no_pii_fields(db_session: AsyncSession):
    """get_order çıktısı PII içermemeli: customer_name, phone, email alanı olmamalı."""
    ctx = _make_ctx(db_session)

    result = await get_order(ctx, order_id=1)

    assert result is not None
    assert not hasattr(result, "customer_name"), "OrderInfo PII alan içermemeli"
    assert not hasattr(result, "phone"), "OrderInfo PII alan içermemeli"
    assert not hasattr(result, "email"), "OrderInfo PII alan içermemeli"


# list_shipments_anomaly testleri


@pytest.mark.asyncio
async def test_list_shipments_anomaly_detects_stale_shipment(seeded_db: AsyncSession):
    """
    Seed: TEST-TRK-ANOMALY 10 saat önce güncellendi, eşik 6 saat.
    list_shipments_anomaly(older_than_hours=6) bu kargoyu anomali olarak bulmalı.
    """
    ctx = _make_ctx(seeded_db)

    anomalies = await list_shipments_anomaly(ctx, older_than_hours=6)

    tracking_ids = [a.tracking_id for a in anomalies]
    assert "TEST-TRK-ANOMALY" in tracking_ids, (
        "10 saat önce güncellenen in_transit kargo anomali listesinde olmalı"
    )


@pytest.mark.asyncio
async def test_list_shipments_anomaly_excludes_recent_shipment(seeded_db: AsyncSession):
    """
    Seed: TEST-TRK-NORMAL 2 saat önce güncellendi, eşik 6 saat.
    Bu kargo anomali listesine girmemeli.
    """
    ctx = _make_ctx(seeded_db)

    anomalies = await list_shipments_anomaly(ctx, older_than_hours=6)

    tracking_ids = [a.tracking_id for a in anomalies]
    assert "TEST-TRK-NORMAL" not in tracking_ids, (
        "2 saat önce güncellenen kargo 6 saatlik eşikte anomali sayılmamalı"
    )


@pytest.mark.asyncio
async def test_list_shipments_anomaly_result_has_no_pii(seeded_db: AsyncSession):
    """ShipmentAnomaly nesneleri customer_name, phone, email içermemeli."""
    ctx = _make_ctx(seeded_db)

    anomalies = await list_shipments_anomaly(ctx, older_than_hours=6)

    for anomaly in anomalies:
        assert not hasattr(anomaly, "customer_name"), "ShipmentAnomaly PII içermemeli"
        assert not hasattr(anomaly, "phone"), "ShipmentAnomaly PII içermemeli"
        assert hasattr(anomaly, "order_id"), "ShipmentAnomaly order_id içermeli"
        assert hasattr(anomaly, "waited_hours"), "ShipmentAnomaly waited_hours içermeli"


@pytest.mark.asyncio
async def test_list_shipments_anomaly_returns_list(seeded_db: AsyncSession):
    """list_shipments_anomaly her zaman list döndürmeli (boş da olsa)."""
    ctx = _make_ctx(seeded_db)

    result = await list_shipments_anomaly(ctx, older_than_hours=6)

    assert isinstance(result, list), "Dönüş tipi list olmalı"


@pytest.mark.asyncio
async def test_list_shipments_anomaly_high_threshold_returns_empty(seeded_db: AsyncSession):
    """
    older_than_hours=1000 eşiğiyle, seed edilen hiçbir kargo bu kadar eski değil.
    Sonuç, seed verilerinden TEST-TRK-* kayıtlarını içermemeli.
    """
    ctx = _make_ctx(seeded_db)

    anomalies = await list_shipments_anomaly(ctx, older_than_hours=1000)

    tracking_ids = [a.tracking_id for a in anomalies]
    assert "TEST-TRK-ANOMALY" not in tracking_ids
    assert "TEST-TRK-NORMAL" not in tracking_ids


# list_low_stock testleri


@pytest.mark.asyncio
async def test_list_low_stock_detects_below_threshold_sku(seeded_db: AsyncSession):
    """
    Seed: TEST-SKU-LOW current_qty=3, threshold=10 → eşik altında.
    list_low_stock bu SKU'yu bulmalı.
    """
    ctx = _make_ctx(seeded_db)

    low_items = await list_low_stock(ctx)

    skus = [item.sku for item in low_items]
    assert "TEST-SKU-LOW" in skus, (
        "current_qty=3 / threshold=10 olan SKU düşük stok listesinde olmalı"
    )


@pytest.mark.asyncio
async def test_list_low_stock_excludes_above_threshold_sku(seeded_db: AsyncSession):
    """
    Seed: TEST-SKU-HIGH current_qty=100, threshold=10 → eşik üstünde.
    Bu SKU düşük stok listesine girmemeli.
    """
    ctx = _make_ctx(seeded_db)

    low_items = await list_low_stock(ctx)

    skus = [item.sku for item in low_items]
    assert "TEST-SKU-HIGH" not in skus, (
        "current_qty=100 / threshold=10 olan SKU düşük stok listesinde olmamalı"
    )


@pytest.mark.asyncio
async def test_list_low_stock_result_contains_supplier_info(seeded_db: AsyncSession):
    """list_low_stock çıktısı supplier_email ve supplier_name içermeli."""
    ctx = _make_ctx(seeded_db)

    low_items = await list_low_stock(ctx)

    test_item = next((i for i in low_items if i.sku == "TEST-SKU-LOW"), None)
    assert test_item is not None, "TEST-SKU-LOW listede olmalı"
    assert test_item.supplier_email == "test@tedarikci.example.com"
    assert test_item.supplier_name == "Test Tedarikçi"
    assert test_item.current_qty == 3
    assert test_item.threshold == 10


@pytest.mark.asyncio
async def test_list_low_stock_returns_list(seeded_db: AsyncSession):
    """list_low_stock her zaman list döndürmeli (boş da olsa)."""
    ctx = _make_ctx(seeded_db)

    result = await list_low_stock(ctx)

    assert isinstance(result, list), "Dönüş tipi list olmalı"


@pytest.mark.asyncio
async def test_list_low_stock_result_has_no_pii(seeded_db: AsyncSession):
    """LowStockItem nesneleri customer PII içermemeli."""
    ctx = _make_ctx(seeded_db)

    low_items = await list_low_stock(ctx)

    for item in low_items:
        assert not hasattr(item, "customer_name"), "LowStockItem PII içermemeli"
        assert not hasattr(item, "phone"), "LowStockItem PII içermemeli"
        assert hasattr(item, "sku"), "LowStockItem sku içermeli"
        assert hasattr(item, "current_qty"), "LowStockItem current_qty içermeli"
        assert hasattr(item, "threshold"), "LowStockItem threshold içermeli"
