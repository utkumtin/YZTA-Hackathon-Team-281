FROM python:3.12-slim

WORKDIR /app

# Sistem gereksinimleri (asyncpg için gcc gerekli)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# uv kurulumu
RUN pip install --no-cache-dir uv

# Bağımlılık dosyalarını önce kopyala (layer cache için)
COPY pyproject.toml .

# Bağımlılıkları kur
RUN uv pip install --system -e ".[dev]"

# Proje kodlarını kopyala
COPY . .

# FastAPI uygulaması 8000 portundan kalkacak
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
