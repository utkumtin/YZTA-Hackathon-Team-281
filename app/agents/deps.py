"""
app/agents/deps.py — AgentDeps: tool'ların runtime bağımlılık konteyneri

Yeni bir runtime bağımlılık (örn. http client, cache) eklenecekse buraya
alan ekle — her tool imzasına ayrı parametre koyma.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class AgentDeps:
    """Tüm tool'ların RunContext[AgentDeps] üzerinden eriştiği runtime context.

    Kullanım (webhook handler içinde):
        async with AsyncSessionLocal() as db:
            deps = AgentDeps(
                db=db,
                owner_chat_id=settings.owner_telegram_id,
                bot_token=settings.telegram_bot_token,
            )
            result = await agent.run(text, deps=deps)

    Kritik kural: AgentDeps'i async with bloğu DIŞINDA oluşturma;
    session context manager'dan çıkınca kapatılır, sonraki await çakışır.
    """

    db: AsyncSession
    owner_chat_id: int  # OWNER_TELEGRAM_ID — env'den int olarak gelir
    bot_token: str  # python-telegram-bot send wrapper'ı için
