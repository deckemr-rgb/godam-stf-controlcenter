"""Konfigurasi Chromium yang dipakai bersama oleh live session & worker Celery.

Tujuannya: satu bot (satu Chromium) seseringan mungkin tanpa mengorbankan
fungsinya. Semua nilai bisa ditimpa lewat environment variable.

Catatan hasil ukur lokal (macOS, halaman instagram.com):
- Chromium headless dasar: ±350-550 MB RSS (paling ditentukan oleh beratnya
  halaman Instagram, bukan flag-nya) dan ±5% CPU saat menganggur.
- Screenshot terus-menerus tiap 0,6s (1280x900, q70) menambah ±6% CPU/1 core.
  Dengan q55 + jeda 0,9s + hanya saat ditonton, tambahannya turun ke ±4%
  (dan 0 kalau tidak ada yang menonton).
"""

from __future__ import annotations

import os

# Flag penghemat memori/CPU + stabilitas di container.
# --disable-dev-shm-usage penting di Docker: /dev/shm kecil dan Chromium bisa
# crash / memakan memori lebih besar kalau dibiarkan memakainya.
DEFAULT_BROWSER_ARGS: tuple[str, ...] = (
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-sync",
    "--disable-default-apps",
    "--disable-translate",
    "--mute-audio",
    "--disable-features=site-per-process,Translate,BackForwardCache,MediaRouter,OptimizationHints",
    "--renderer-process-limit=1",
)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def browser_args() -> list[str]:
    """Flag Chromium. Timpa dengan env LIVE_BROWSER_ARGS (dipisah spasi)."""
    raw = os.getenv("LIVE_BROWSER_ARGS")
    if raw:
        return [arg for arg in raw.split() if arg]
    return list(DEFAULT_BROWSER_ARGS)


def viewport() -> dict[str, int]:
    """Ukuran jendela. Lebih kecil = screenshot lebih ringan & memori turun."""
    try:
        width = max(320, int(os.getenv("LIVE_VIEWPORT_WIDTH", "1000")))
    except ValueError:
        width = 1000
    try:
        height = max(320, int(os.getenv("LIVE_VIEWPORT_HEIGHT", "700")))
    except ValueError:
        height = 700
    return {"width": width, "height": height}


def frame_interval_ms() -> int:
    """Jeda antar screenshot. 0 = matikan streaming gambar (paling hemat)."""
    try:
        value = int(os.getenv("LIVE_FRAME_INTERVAL_MS", "900"))
    except ValueError:
        return 900
    if value <= 0:
        return 0
    return max(200, value)


def frame_quality() -> int:
    try:
        return min(90, max(20, int(os.getenv("LIVE_FRAME_QUALITY", "55"))))
    except ValueError:
        return 55


def frame_idle_ms() -> int:
    """Berhenti screenshot kalau tidak ada yang menonton selama ini (ms)."""
    try:
        return max(1000, int(os.getenv("LIVE_FRAME_IDLE_MS", "3000")))
    except ValueError:
        return 3000


def blocked_resource_types() -> set[str]:
    """Resource yang dibatalkan supaya hemat bandwidth/CPU.

    Font & media selalu dibatalkan (tidak dipakai bot, tampilan tetap wajar).
    Set LIVE_BLOCK_IMAGES=1 untuk ikut membatalkan gambar (paling hemat, tapi
    tampilan Chrome Live jadi kosong/gambar tidak muncul).
    """
    blocked = {"font", "media"}
    if _env_bool("LIVE_BLOCK_IMAGES"):
        blocked.add("image")
    return blocked
