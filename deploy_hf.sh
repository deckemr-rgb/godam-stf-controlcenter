#!/usr/bin/env bash
# ============================================================
# deploy_hf.sh — Deploy backend FastAPI + Celery ke Hugging Face Spaces
#
# Cara pakai (dari folder root proyek):
#   1) ./deploy_hf.sh USERNAME NAMA_SPACE
#      -> nanti diminta token secara interaktif (aman, tidak tampil)
#   atau langsung:
#   2) ./deploy_hf.sh USERNAME NAMA_SPACE hf_TOKEN
#
# Contoh:
#   ./deploy_hf.sh mymac instagram-bot-api
# ============================================================
set -euo pipefail

# --- Warna output (biar enak dibaca) ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# --- Cek git tersedia ---
if ! command -v git >/dev/null 2>&1; then
  error "Git tidak ditemukan. Install dulu: https://git-scm.com"
  exit 1
fi

# --- Ambil input ---
HF_USERNAME="${1:-}"
SPACE_NAME="${2:-}"
HF_TOKEN="${3:-}"

if [[ -z "$HF_USERNAME" ]]; then
  read -r -p "Username Hugging Face kamu: " HF_USERNAME
fi
if [[ -z "$SPACE_NAME" ]]; then
  read -r -p "Nama Space (mis. instagram-bot-api): " SPACE_NAME
fi
if [[ -z "$HF_TOKEN" ]]; then
  read -r -s -p "Token Hugging Face (tidak akan ditampilkan): " HF_TOKEN
  echo ""
fi

if [[ -z "$HF_USERNAME" || -z "$SPACE_NAME" || -z "$HF_TOKEN" ]]; then
  error "Username, nama Space, dan token wajib diisi."
  exit 1
fi

# --- Lokasi folder backend (folder ini = root proyek) ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"

# --- Daftar file yang wajib dikirim ke Space ---
FILES_TO_COPY=(
  "main.py"
  "celery_app.py"
  "tasks.py"
  "live_session.py"
  "requirements.txt"
  "Dockerfile"
  "start.sh"
  ".dockerignore"
  "README.md"
)

# --- Validasi file backend ada semua ---
info "Memeriksa file backend di: $BACKEND_DIR"
for f in "${FILES_TO_COPY[@]}"; do
  if [[ ! -f "$BACKEND_DIR/$f" ]]; then
    error "File tidak ditemukan: backend/$f"
    exit 1
  fi
done
info "Semua file backend ditemukan."

# --- Buat folder sementara untuk clone Space ---
TMP_DIR="$(mktemp -d)"
SPACE_DIR="$TMP_DIR/$SPACE_NAME"
cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT

SPACE_URL="https://${HF_USERNAME}:${HF_TOKEN}@huggingface.co/spaces/${HF_USERNAME}/${SPACE_NAME}"

info "Meng-clone Space: ${HF_USERNAME}/${SPACE_NAME} ..."
if ! git clone --quiet "$SPACE_URL" "$SPACE_DIR"; then
  error "Gagal clone Space. Cek: username, nama Space, dan token (harus berjenis Write)."
  exit 1
fi

# --- Salin semua file backend ke Space ---
info "Menyalin file backend ke Space ..."
for f in "${FILES_TO_COPY[@]}"; do
  cp "$BACKEND_DIR/$f" "$SPACE_DIR/$f"
  info "  -> $f"
done

# --- Commit & push ---
cd "$SPACE_DIR"

# Set identity lokal agar git tidak error
git config user.email "deploy@hf.local"
git config user.name "$HF_USERNAME"

if git diff --quiet && git diff --cached --quiet; then
  warn "Tidak ada perubahan file. Tidak ada yang di-push."
  exit 0
fi

git add -A
git commit --quiet -m "Deploy backend FastAPI + Celery worker"
info "Mendorong ke Hugging Face ..."
if ! git push --quiet origin main; then
  error "Gagal push. Cek koneksi internet / izin token."
  exit 1
fi

info "=============================================="
info "Deploy berhasil dikirim! 🎉"
info "Cek status build di: https://huggingface.co/spaces/${HF_USERNAME}/${SPACE_NAME}"
info "Health check: https://${HF_USERNAME}-${SPACE_NAME}.hf.space/health"
info "=============================================="
