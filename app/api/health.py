"""
app/api/health.py — /health endpoint
"""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health", summary="Uygulama sağlık kontrolü")
async def health_check() -> dict[str, str]:
    """Uygulamanın ayakta olduğunu doğrular.

    Docker healthcheck ve smoke test'lerin başlangıç noktası.
    DB bağlantısı lifespan'de test edildiği için burada ayrıca check yok.
    """
    return {"status": "ok"}
