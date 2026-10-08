#!/usr/bin/env bash
# Jalankan backend "via PC" di laptop sendiri (macOS / Linux).
# Aman dijalankan berulang-ulang.
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 belum terinstall. Install dulu dari https://python.org lalu ulangi."
  exit 1
fi

# 1) Buat .env bila belum ada (DEBUG=true penting supaya CORS diizinkan).
if [ ! -f .env ]; then
  echo "Membuat .env ..."
  cat > .env <<'EOF'
DEBUG=true
HOST=0.0.0.0
PORT=8000
FRONTEND_URL=http://localhost:3000
REDIS_URL=redis://localhost:6379/0
CREDENTIAL_ENCRYPTION_KEY=
LIVE_HEADLESS=true
PLAYWRIGHT_TIMEOUT_MS=10000
PLAYWRIGHT_NAVIGATION_TIMEOUT_MS=30000
LOG_LEVEL=INFO
EOF
fi

# 2) Siapkan venv bila belum ada.
if [ ! -d .venv ]; then
  echo "Membuat venv ..."
  python3 -m venv .venv
fi

# 3) Aktifkan & pastikan dependensi terpasang.
# shellcheck disable=SC1091
source .venv/bin/activate
echo "Menginstall dependensi ..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# 4) Pastikan Chromium Playwright tersedia.
python -m playwright install chromium

# 5) Jalankan server.
echo "=============================================="
echo "  Backend VIA PC siap! Jangan tutup jendela ini."
echo "  Buka https://godam-omega.vercel.app lalu pilih via PC"
echo "=============================================="
exec uvicorn main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
