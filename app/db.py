"""
app/db.py — Async veritabanı engine ve session factory

Kullanım:
    async with AsyncSessionLocal() as db:
        result = await db.execute(...)
"""

import sqlalchemy
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

# ── Engine ────────────────────────────────────────────────────────────────────
# pool_pre_ping: connection drop'larında otomatik yeniden bağlan
engine: AsyncEngine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=settings.log_level == "DEBUG",
)

# ── Session factory ──────────────────────────────────────────────────────────
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,  # commit sonrası attribute erişimi için gerekli
    autoflush=False,
    autocommit=False,
)


async def check_db_connection() -> None:
    """Lifespan'de DB bağlantısını doğrular; hata varsa uygulama başlamaz."""
    async with engine.connect() as conn:
        await conn.execute(sqlalchemy.text("SELECT 1"))
