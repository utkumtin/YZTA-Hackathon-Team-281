"""
app/main.py — FastAPI uygulama girişi

Lifespan sırası:
    1. Logger yapılandırması (import ile tetiklenir)
    2. DB bağlantı testi
    3. Telegram bot başlatma (polling veya webhook modu)
    4. Router'ları include et
    5. Shutdown: bot session'ı kapat
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

# Logging modülü import edilir edilmez root logger yapılandırılır
import app.logging  # noqa: F401

# Router imports
from app.api.health import router as health_router
from app.config import settings
from app.db import check_db_connection
from app.logging import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Uygulama başlangıç ve kapanış lifecycle'ı."""

    # ── Startup ──────────────────────────────────────────────────────────────
    logger.info("startup_begin", extra={"env": settings.env, "log_level": settings.log_level})

    # 1. DB bağlantı testi
    try:
        await check_db_connection()
        logger.info("db_connection_ok", extra={"database_url": _mask_url(settings.database_url)})
    except Exception as exc:
        logger.error("db_connection_failed", extra={"error": str(exc)})
        raise

    # 2. Telegram bot hazırla (polling / webhook)
    if settings.telegram_bot_token:
        _setup_telegram()
    else:
        logger.warning(
            "telegram_bot_token_missing",
            extra={"hint": "Set TELEGRAM_BOT_TOKEN in .env to enable Telegram"},
        )

    logger.info("startup_complete", extra={"demo_mode": settings.demo_mode_enabled})

    yield  # uygulama burada çalışır

    # ── Shutdown ─────────────────────────────────────────────────────────────
    logger.info("shutdown_begin")
    logger.info("shutdown_complete")


def _setup_telegram() -> None:
    """Telegram bot kurulumu"""
    logger.info(
        "telegram_setup",
        extra={
            "mode": "polling" if settings.use_polling else "webhook",
            "owner_chat_id": settings.owner_telegram_id,
        },
    )


def _mask_url(url: str) -> str:
    """Log'a yazılacak DB URL'deki şifreyi maskeler."""
    try:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url)
        if parsed.password:
            netloc = parsed.netloc.replace(f":{parsed.password}@", ":***@")
            return urlunparse(parsed._replace(netloc=netloc))
    except Exception:
        pass
    return url


# ── FastAPI uygulaması ────────────────────────────────────────────────────────

app = FastAPI(
    title="KOBİ Operasyon Otomasyonu",
    description=(
        "AI Destekli KOBİ Operasyon Otomasyonu — Hackathon MVP\n\n"
        "Telegram üzerinden müşteri destek + proaktif kargo/stok izleme."
    ),
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.env != "prod" else None,
    redoc_url="/redoc" if settings.env != "prod" else None,
)

# ── Router kayıtları ──────────────────────────────────────────────────────────
app.include_router(health_router)
