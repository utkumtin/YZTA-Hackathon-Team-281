#!/usr/bin/env bash
# scripts/set_webhook.sh — Telegram webhook'u ngrok URL'sine kaydeder.
#
# Kullanım:
#   ./scripts/set_webhook.sh <ngrok-url>
#
# Örnek:
#   ./scripts/set_webhook.sh https://abc123.ngrok-free.app
#
# Gereksinimler:
#   - .env dosyasında TELEGRAM_BOT_TOKEN ve TELEGRAM_WEBHOOK_SECRET dolu olmalı.
#   - curl yüklü olmalı.

set -euo pipefail

# ── .env'den değerleri oku ────────────────────────────────────────────────────
if [ -f ".env" ]; then
    export $(grep -v '^#' .env | grep -v '^$' | xargs)
fi

NGROK_URL="${1:-}"

if [ -z "$NGROK_URL" ]; then
    echo "Kullanım: $0 <ngrok-url>"
    echo "Örnek:    $0 https://abc123.ngrok-free.app"
    exit 1
fi

if [ -z "${TELEGRAM_BOT_TOKEN:-}" ]; then
    echo "HATA: TELEGRAM_BOT_TOKEN .env'de tanımlı değil."
    exit 1
fi

WEBHOOK_URL="${NGROK_URL}/telegram/webhook"

echo "──────────────────────────────────────────"
echo "Bot Token : ${TELEGRAM_BOT_TOKEN:0:10}..."
echo "Webhook   : ${WEBHOOK_URL}"
echo "──────────────────────────────────────────"

# ── setWebhook ────────────────────────────────────────────────────────────────
echo ""
echo "▶ setWebhook çağrılıyor..."

SET_RESULT=$(curl -s -X POST \
    "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
    -d "url=${WEBHOOK_URL}" \
    ${TELEGRAM_WEBHOOK_SECRET:+-d "secret_token=${TELEGRAM_WEBHOOK_SECRET}"})

echo "$SET_RESULT"

OK=$(echo "$SET_RESULT" | grep -o '"ok":true' || true)
if [ -z "$OK" ]; then
    echo ""
    echo "HATA: setWebhook başarısız. Yukarıdaki Telegram yanıtını kontrol et."
    exit 1
fi

echo ""
echo "✅ Webhook başarıyla ayarlandı."

# ── getWebhookInfo — doğrulama ────────────────────────────────────────────────
echo ""
echo "▶ getWebhookInfo ile doğrulanıyor..."

curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo" \
    | python3 -m json.tool 2>/dev/null || \
  curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"

echo ""
echo "──────────────────────────────────────────"
echo "Webhook kurulumu tamamlandı."
echo "Kontrol: pending_update_count sıfırsa hazırsın."
echo "──────────────────────────────────────────"
