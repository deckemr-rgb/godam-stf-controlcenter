@echo off
REM Jalankan backend "via PC" di laptop sendiri (Windows).
REM Aman dijalankan berulang-ulang.
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo Python belum terinstall. Install dari https://python.org
  echo PENTING: centang "Add Python to PATH" saat install.
  pause
  exit /b 1
)

REM 1) Buat .env bila belum ada (DEBUG=true penting untuk CORS).
if not exist .env (
  echo Membuat .env ...
  (
    echo DEBUG=true
    echo HOST=0.0.0.0
    echo PORT=8000
    echo FRONTEND_URL=http://localhost:3000
    echo REDIS_URL=redis://localhost:6379/0
    echo CREDENTIAL_ENCRYPTION_KEY=
    echo LIVE_HEADLESS=true
    echo PLAYWRIGHT_TIMEOUT_MS=10000
    echo PLAYWRIGHT_NAVIGATION_TIMEOUT_MS=30000
    echo LOG_LEVEL=INFO
  ) > .env
)

REM 2) Siapkan venv bila belum ada.
if not exist .venv (
  echo Membuat venv ...
  python -m venv .venv
)

REM 3) Aktifkan & install dependensi.
call .venv\Scripts\activate.bat
echo Menginstall dependensi ...
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

REM 4) Pastikan Chromium Playwright tersedia.
python -m playwright install chromium

REM 5) Jalankan server.
echo ==============================================
echo   Backend VIA PC siap! Jangan tutup jendela ini.
echo   Buka https://godam-omega.vercel.app lalu pilih via PC
echo ==============================================
uvicorn main:app --host %HOST% --port %PORT%
pause
