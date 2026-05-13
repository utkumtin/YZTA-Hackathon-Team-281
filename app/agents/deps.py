"""
app/agents/deps.py — AgentDeps: tool'ların runtime bağımlılık konteyneri

Yeni bir runtime bağımlılık (örn. http client, cache) eklenecekse buraya
alan ekle — her tool imzasına ayrı parametre koyma.
"""

import asyncio
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class AgentDeps:
    """Tüm tool'ların RunContext[AgentDeps] üzerinden eriştiği runtime context.

    Kullanım:
        async with AsyncSessionLocal() as db:
            deps = AgentDeps(
                db=db,
                owner_chat_id=settings.owner_telegram_id,
                bot_token=settings.telegram_bot_token,
            )
            result = await agent.run(text, deps=deps)

    Kritik kurallar:
    - AgentDeps'i async with bloğu DIŞINDA oluşturma.
      Session context manager'dan çıkınca kapatılır.
    - Aynı AsyncSession üzerinde eş zamanlı DB işlemi yapılmamalıdır.
      PydanticAI bazı tool çağrılarını paralel çalıştırabildiği için DB kullanan
      tool'lar ctx.deps.db_lock ile DB işlemlerini sıraya almalıdır.
    """

    db: AsyncSession
    owner_chat_id: int | None = None  # OWNER_TELEGRAM_ID — env'den gelir
    bot_token: str | None = None  # python-telegram-bot send wrapper'ı için
    db_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
