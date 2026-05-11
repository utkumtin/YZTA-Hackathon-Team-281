FROM python:3.12-slim

WORKDIR /app

# Sistem gereksinimleri (örneğin asyncpg veya uv için gerekli olabilecek paketler)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# uv kurulumu (daha hızlı paket yönetimi için)
RUN pip install uv

# Bağımlılıkları kopyala ve kur
COPY pyproject.toml .
# uv pip install kullanarak bağımlılıkları yükle (veya pyproject.toml henüz tam değilse temel paketleri yükleyelim)
# Şimdilik standart pip de kullanılabilir:
RUN uv pip install --system fastapi uvicorn pydantic-ai python-telegram-bot asyncpg sqlalchemy pydantic-settings

# Proje kodlarını kopyala
COPY . .

# FastAPI uygulaması 8000 portundan kalkacak
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
