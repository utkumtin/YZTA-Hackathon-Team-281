"""
app/config.py — Uygulama konfigürasyonu

Tüm env değişkenleri bu modülden okunur. Başka hiçbir yerde os.getenv / os.environ
kullanılmaz — her zaman `from app.config import settings` ile erişilir.
"""

from functools import lru_cache
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Telegram ────────────────────────────────────────────────────────────
    telegram_bot_token: str = ""
    owner_telegram_id: int = 0
    telegram_webhook_secret: str = ""
    use_polling: bool = False
    demo_customer_tg_id: int = 0

    # ── LLM ─────────────────────────────────────────────────────────────────
    gemini_api_key: str = ""
    llm_provider: str = "gemini"
    llm_model: str = "gemini-2.5-flash"

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://kobi:kobi@db:5432/kobi_db"

    # ── Observability ────────────────────────────────────────────────────────
    log_level: str = "INFO"
    logfire_token: str = ""

    # ── Demo & Environment ───────────────────────────────────────────────────
    env: str = "demo"
    demo_mode_enabled: bool = True

    @field_validator("owner_telegram_id", mode="before")
    @classmethod
    def parse_owner_id(cls, v: object) -> object:
        """OWNER_TELEGRAM_ID string gelirse int'e çevir; Telegram integer ister."""
        if isinstance(v, str) and v.strip() == "":
            return 0
        return v

    @field_validator("demo_customer_tg_id", mode="before")
    @classmethod
    def parse_customer_tg_id(cls, v: object) -> object:
        if isinstance(v, str) and v.strip() == "":
            return 0
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton settings — her yerde aynı nesneyi döndürür."""
    return Settings()


# Modül seviyesinde erişim kolaylığı: `from app.config import settings`
settings: Settings = get_settings()
