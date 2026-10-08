#!/usr/bin/env bash
# Jalankan sekali di VPS sebagai root.
set -euo pipefail

APP_DIR=/opt/godam
REPO_URL="${REPO_URL:-https://github.com/uppvision-lgtm/godam.git}"

if ! command -v docker >/dev/null 2>&1; then
  echo "==> Menginstal Docker..."
  curl -fsSL https://get.docker.com | sh
  systemctl enable --now docker
fi

if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"
git checkout main
git pull --ff-only origin main || true

if [ ! -f .env ]; then
  cat > .env <<'ENV'
DEBUG=false
FRONTEND_URL=https://auto-comment.tech,https://www.auto-comment.tech
ACME_EMAIL=admin@auto-comment.tech
CREDENTIAL_ENCRYPTION_KEY=
SECRET_KEY=
LOG_LEVEL=INFO
ENV
  echo "==> Edit $APP_DIR/.env — isi CREDENTIAL_ENCRYPTION_KEY dan SECRET_KEY"
  echo "    python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
  exit 0
fi

docker compose up -d --build --remove-orphans
echo "==> Selesai. Cek: docker compose ps"
