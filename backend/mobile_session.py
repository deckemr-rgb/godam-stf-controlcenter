"""Eksekusi fitur Godam langsung pada perangkat Android DeviceFarmer STF.

Modul ini sengaja memakai ADB + accessibility tree bawaan Android. Dengan
begitu provider STF tetap menjadi pemilik perangkat/reservasi, sementara Godam
menjadi orchestrator untuk komentar, like, unggah video, log, dan live frame.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import subprocess
import time
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

from fastapi import HTTPException
from PIL import Image

from stf_api import DEVICE_FIELDS, _request


logger = logging.getLogger("mobile")
ADB_HOST = os.getenv("STF_ADB_HOST", "stf-adb").strip()
ADB_PORT = int(os.getenv("STF_ADB_PORT", "5037"))
ADB_TIMEOUT = float(os.getenv("STF_ADB_TIMEOUT_SECONDS", "30"))
INSTAGRAM_PACKAGE = os.getenv("INSTAGRAM_ANDROID_PACKAGE", "com.instagram.android").strip()

# Posisi elemen feed Reels Instagram, sebagai fraksi dari ukuran layar nyata.
# Diukur dari perangkat sungguhan; uiautomator dump tidak bisa dipakai di
# feed reel karena video membuat UI tidak pernah idle.
REEL_COMMENT_POS = (0.912, 0.281)   # ikon komentar pada rail kanan
REEL_LIKE_POS = (0.912, 0.169)      # hati like pada rail kanan
REEL_FIELD_POS = (0.46, 0.883)      # kotak "Add comment" pada sheet komentar
REEL_HEART_BOX = (0.86, 0.12, 0.96, 0.24)  # area hati like untuk deteksi warna
REEL_HEART_MIN_RED = 120            # piksel merah minimum agar dianggap sudah disukai


@dataclass(frozen=True)
class PlatformSpec:
    label: str
    packages: tuple[str, ...]
    profile_url: str
    like_patterns: tuple[str, ...]
    comment_patterns: tuple[str, ...]
    editor_patterns: tuple[str, ...]
    submit_patterns: tuple[str, ...]
    # Share: tombol utama lalu opsi lanjutan yang aman (jangan pernah menyentuh
    # kontak/DM). Repost: X punya tombol langsung; TikTok/Facebook lewat sheet
    # share; Instagram/Threads tidak punya repost sehingga tidak didukung.
    share_patterns: tuple[str, ...] = ()
    share_confirm_patterns: tuple[str, ...] = ()
    repost_patterns: tuple[str, ...] = ()
    repost_via_share_sheet: bool = False


_COPY_LINK_PATTERNS = (r"^copy link$", r"^salin tautan$", r"^salin link$")
_SHARE_SHEET_DELAY_NOTE = "Sheet share terbuka tetapi tidak ada opsi aman; sheet ditutup tanpa aksi."

PLATFORMS: dict[str, PlatformSpec] = {
    "instagram": PlatformSpec(
        "Instagram",
        (INSTAGRAM_PACKAGE,),
        "https://www.instagram.com/{target}/",
        (r"^like$", r"^suka$"),
        (r"^comment$", r"^komentar$", r"add a comment"),
        (r"comment", r"komentar", r"caption", r"keterangan"),
        (r"^post$", r"^kirim$", r"^send$", r"publish"),
        share_patterns=(r"^share$", r"^bagikan$"),
        share_confirm_patterns=_COPY_LINK_PATTERNS,
    ),
    "tiktok": PlatformSpec(
        "TikTok",
        ("com.zhiliaoapp.musically", "com.ss.android.ugc.trill"),
        "https://www.tiktok.com/@{target}",
        # Rail video TikTok memakai deskripsi panjang, mis.
        # "Like video. 415 likes" — pola ^like$ murni tidak pernah cocok.
        (r"^like video", r"^like$", r"^suka$"),
        (r"add comments", r"comment", r"komentar"),
        (r"add comment", r"tambahkan komentar", r"comment", r"komentar"),
        (r"^send$", r"^kirim$", r"^post$", r"^post comment"),
        share_patterns=(r"share video", r"^share$", r"^bagikan$"),
        share_confirm_patterns=_COPY_LINK_PATTERNS,
        repost_patterns=(r"^repost",),
        repost_via_share_sheet=True,
    ),
    "x": PlatformSpec(
        "X",
        ("com.twitter.android",),
        "https://x.com/{target}",
        (r"^like$", r"^suka$"),
        (r"^reply$", r"^balas$", r"comment", r"komentar"),
        (r"post your reply", r"kirim balasan", r"reply", r"balas"),
        (r"^reply$", r"^balas$", r"^post$", r"^kirim$"),
        share_patterns=(r"^share$", r"^bagikan$"),
        share_confirm_patterns=_COPY_LINK_PATTERNS,
        repost_patterns=(r"^repost$",),
    ),
    "facebook": PlatformSpec(
        "Facebook",
        ("com.facebook.katana",),
        "https://www.facebook.com/{target}",
        (r"^like$", r"^suka$"),
        (r"^comment$", r"^komentar$", r"write a comment"),
        (r"write a comment", r"tulis komentar", r"comment", r"komentar"),
        (r"^post$", r"^kirim$", r"^send$"),
        share_patterns=(r"^share$", r"^bagikan$"),
        share_confirm_patterns=(
            r"^share now",
            r"^bagikan sekarang",
            r"share to feed",
            r"bagikan ke feed",
        ) + _COPY_LINK_PATTERNS,
        repost_patterns=(r"^share now", r"^bagikan sekarang", r"share to feed", r"bagikan ke feed"),
        repost_via_share_sheet=True,
    ),
    "threads": PlatformSpec(
        "Threads",
        ("com.instagram.barcelona",),
        "https://www.threads.net/@{target}",
        (r"^like$", r"^suka$"),
        (r"^reply$", r"^balas$", r"comment", r"komentar"),
        (r"reply", r"balas", r"comment", r"komentar"),
        (r"^post$", r"^kirim$", r"^reply$", r"^balas$"),
        share_patterns=(r"^share$", r"^bagikan$", r"^send$", r"^kirim$"),
        share_confirm_patterns=_COPY_LINK_PATTERNS,
    ),
}


# Aksi engagement yang dikenal sistem. Urutan inilah urutan eksekusi per post.
ACTION_LABELS: dict[str, str] = {
    "like": "Like",
    "comment": "Komentar",
    "share": "Share",
    "repost": "Repost",
}
ACTION_ORDER: tuple[str, ...] = tuple(ACTION_LABELS)
# Repost native hanya ada di X, TikTok, dan Facebook.
REPOST_PLATFORMS = frozenset(platform_id for platform_id, spec in PLATFORMS.items() if spec.repost_patterns)


def supported_actions(platform: str) -> tuple[str, ...]:
    """Aksi yang valid untuk satu platform, dalam urutan eksekusi."""
    if platform not in PLATFORMS:
        raise ValueError(f"Platform tidak didukung: {platform}")
    return tuple(action for action in ACTION_ORDER if action != "repost" or platform in REPOST_PLATFORMS)


def normalize_actions(platform: str, actions: Iterable[str] | None) -> list[str]:
    """Bersihkan daftar aksi dari API: urutkan, hapus duplikat, tolak yang ilegal."""
    if actions is None:
        return ["like", "comment"]
    requested = {str(action).strip().lower() for action in actions if str(action).strip()}
    allowed = set(supported_actions(platform))
    unknown = sorted(requested - allowed)
    if unknown:
        raise ValueError(
            "Aksi tidak didukung untuk platform ini: " + ", ".join(unknown)
            + f". Aksi valid: {', '.join(sorted(allowed))}."
        )
    return [action for action in ACTION_ORDER if action in requested] or ["like", "comment"]


def platform_action_options(platform: str) -> list[dict[str, Any]]:
    """Daftar aksi untuk UI: id, label, dan ketersediaan di platform ini."""
    allowed = set(supported_actions(platform))
    return [
        {"id": action, "label": ACTION_LABELS[action], "supported": action in allowed}
        for action in ACTION_ORDER
    ]


class MobileAutomationError(RuntimeError):
    pass


@dataclass
class UiNode:
    text: str
    description: str
    class_name: str
    clickable: bool
    bounds: tuple[int, int, int, int]

    @property
    def label(self) -> str:
        return " ".join(value for value in (self.text, self.description) if value).strip()

    @property
    def center(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return ((left + right) // 2, (top + bottom) // 2)


class MobileSession:
    execution_target = "stf"
    frame_media_type = "image/jpeg"

    def __init__(self, token: str, serial: str) -> None:
        self.token = token
        self.device_serial = serial
        self.status = "starting"
        self.message = "Menyiapkan perangkat STF..."
        self.logs: list[str] = []
        self.result: dict[str, Any] | None = None
        self.width = 360
        self.height = 720
        self.latest_jpeg: bytes | None = None
        self._running = True
        self._task: asyncio.Task[None] | None = None
        self._reserved_here = False

    def add_log(self, text: str) -> None:
        self.logs.append(text)
        if len(self.logs) > 300:
            del self.logs[:-300]
        logger.info("[%s/%s] %s", self.token[:6], self.device_serial, text)

    def is_browser_alive(self) -> bool:
        return self._running and self.status in {"starting", "running"}

    async def start_comment(
        self,
        username: str,
        target: str,
        comment_count: int,
        max_posts: int,
        tone: str,
    ) -> None:
        await self.start_engagement(
            "instagram", username, target, comment_count, max_posts, tone
        )

    async def start_engagement(
        self,
        platform: str,
        username: str,
        target: str,
        comment_count: int,
        max_posts: int,
        tone: str,
        actions: Iterable[str] | None = None,
    ) -> None:
        platform = platform.strip().lower()
        if platform not in PLATFORMS:
            raise MobileAutomationError(f"Platform tidak didukung: {platform}")
        self._task = asyncio.create_task(
            asyncio.to_thread(
                self._run_engagement,
                platform,
                username,
                target,
                comment_count,
                max_posts,
                tone,
                normalize_actions(platform, actions),
            )
        )

    async def start_upload(self, username: str, berkas: str, caption: str) -> None:
        self._task = asyncio.create_task(
            asyncio.to_thread(self._run_upload, username, berkas, caption)
        )

    async def close(self) -> None:
        self._running = False
        self.status = "stopped"
        self.message = "Eksekusi perangkat dihentikan."
        await asyncio.to_thread(self._release)

    def _adb(
        self,
        *args: str,
        timeout: float | None = None,
        raw: bool = False,
        check: bool = True,
    ) -> str | bytes:
        command = [
            "adb",
            "-H",
            ADB_HOST,
            "-P",
            str(ADB_PORT),
            "-s",
            self.device_serial,
            *args,
        ]
        try:
            result = subprocess.run(
                command,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout or ADB_TIMEOUT,
            )
        except FileNotFoundError as error:
            raise MobileAutomationError("ADB belum terpasang di backend Godam.") from error
        except subprocess.TimeoutExpired as error:
            raise MobileAutomationError("Perangkat tidak merespons sebelum timeout ADB.") from error
        if check and result.returncode:
            detail = result.stderr.decode("utf-8", "replace").strip() or "perintah ADB gagal"
            raise MobileAutomationError(detail[:300])
        if raw:
            return result.stdout
        return result.stdout.decode("utf-8", "replace").strip()

    def _reserve(self) -> None:
        detail = _request(
            "GET",
            f"/api/v1/devices/{quote(self.device_serial, safe='')}",
            params={"fields": DEVICE_FIELDS},
        )
        device = detail.get("device", detail)
        if not device.get("present") or not device.get("ready"):
            raise MobileAutomationError("Perangkat STF sedang offline atau belum siap.")

        reservations = _request(
            "GET", "/api/v1/user/devices", params={"fields": DEVICE_FIELDS}
        ).get("devices", [])
        if any(item.get("serial") == self.device_serial for item in reservations):
            self.add_log("Memakai reservasi STF yang sudah aktif.")
            return

        _request(
            "POST",
            "/api/v1/user/devices",
            json={"serial": self.device_serial, "timeout": 3_600_000},
        )
        self._reserved_here = True
        self.add_log("Perangkat berhasil direservasi lewat STF.")

    def _release(self) -> None:
        if not self._reserved_here:
            return
        self._reserved_here = False
        try:
            _request(
                "DELETE",
                f"/api/v1/user/devices/{quote(self.device_serial, safe='')}",
            )
            self.add_log("Reservasi otomatis dilepas.")
        except Exception as error:
            logger.warning("Gagal melepas %s: %s", self.device_serial, error)

    def _prepare(self, packages: tuple[str, ...] = (INSTAGRAM_PACKAGE,)) -> str:
        self._reserve()
        state = str(self._adb("get-state"))
        if state.strip() != "device":
            raise MobileAutomationError(
                "Perangkat terdaftar di STF tetapi belum terlihat oleh ADB provider."
            )
        package = next(
            (
                candidate
                for candidate in packages
                if str(self._adb("shell", "pm", "path", candidate, check=False)).strip()
            ),
            "",
        )
        if not package:
            raise MobileAutomationError(
                "Aplikasi sosial untuk platform yang dipilih belum terpasang pada perangkat."
            )
        self._adb("shell", "input", "keyevent", "KEYCODE_WAKEUP", check=False)
        self._adb("shell", "wm", "dismiss-keyguard", check=False)
        # Animasi transisi membuat uiautomator menunggu "idle" lebih lama;
        # matikan selama automasi agar dump lebih konsisten.
        for setting in ("window_animation_scale", "transition_animation_scale", "animator_duration_scale"):
            self._adb("shell", "settings", "put", "global", setting, "0", check=False)
        size = str(self._adb("shell", "wm", "size", check=False))
        match = re.search(r"(\d+)x(\d+)", size)
        if match:
            self.width, self.height = int(match.group(1)), int(match.group(2))
        # Ukuran yang sah untuk input tap adalah ruang layar nyata dari
        # screencap, bukan selalu resolusi fisik dari `wm size`.
        shot = self._shot_image()
        if shot is not None:
            self.width, self.height = shot.size
        self._current_package = package
        self._capture()
        return package

    def _capture(self) -> None:
        try:
            png = self._adb("exec-out", "screencap", "-p", raw=True, timeout=15)
            if not png:
                return
            with Image.open(io.BytesIO(png)) as image:
                image.thumbnail((720, 1280))
                output = io.BytesIO()
                image.convert("RGB").save(output, format="JPEG", quality=72, optimize=True)
                self.latest_jpeg = output.getvalue()
        except Exception:
            logger.debug("Screenshot ADB gagal", exc_info=True)

    def _shot_image(self) -> Image.Image | None:
        """Screenshot resolusi penuh sebagai gambar PIL (ruang koordinat input)."""
        try:
            png = self._adb("exec-out", "screencap", "-p", raw=True, timeout=15)
            if not png:
                return None
            return Image.open(io.BytesIO(png)).convert("RGB")
        except Exception:
            logger.debug("Screencap resolusi penuh gagal", exc_info=True)
            return None

    @staticmethod
    def _count_red_in_box(image: Image.Image, box: tuple[float, float, float, float]) -> int:
        """Hitung piksel 'merah Instagram' (hati like aktif) pada kotak fraksi layar."""
        width, height = image.size
        left = int(width * box[0])
        top = int(height * box[1])
        right = int(width * box[2])
        bottom = int(height * box[3])
        pixels = image.crop((left, top, right, bottom)).getdata()
        return sum(1 for red, green, blue in pixels if red > 200 and green < 90 and blue < 130)

    def _reel_like_state(self) -> bool | None:
        """Deteksi hati like reel: True sudah disukai, False belum, None tak pasti."""
        image = self._shot_image()
        if image is None:
            return None
        return self._count_red_in_box(image, REEL_HEART_BOX) >= REEL_HEART_MIN_RED

    def _double_tap(self, x: int, y: int) -> None:
        # Dua tap dalam satu panggilan shell agar jeda keduanya < 300 ms dan
        # dihitung Android sebagai double-tap.
        self._adb("shell", f"input tap {x} {y}; input tap {x} {y}")

    def _reel_like(self) -> bool:
        """Like reel: tap posisi hati pada rail kanan + verifikasi warna.

        Koordinat hati (0.912w, 0.169h) diukur dari perangkat sungguhan dan
        jauh lebih andal daripada double-tap yang sering tidak terhitung
        karena jeda antar perintah `input tap`.
        """
        state = self._reel_like_state()
        if state is True:
            # Konfirmasi sekali lagi: saat pergantian reel, frame basi reel
            # sebelumnya (yang merah) bisa saja masih tertangkap layar.
            time.sleep(1.5)
            if self._reel_like_state() is True:
                self.add_log("Reel sudah disukai sebelumnya; like dilewati agar tidak batal.")
                return True
        heart = (int(self.width * REEL_LIKE_POS[0]), int(self.height * REEL_LIKE_POS[1]))
        self._tap_xy(*heart)
        time.sleep(1.5)
        verified = self._reel_like_state()
        if verified is True:
            return True
        # Cadangan: double-tap tengah video.
        self._double_tap(self.width // 2, self.height // 2)
        time.sleep(1.5)
        verified = self._reel_like_state()
        if verified is True:
            return True
        self.add_log("Like dikirim tetapi hati merah tidak terdeteksi di layar.")
        return False

    def _find_ig_blue(self, image: Image.Image) -> tuple[int, int] | None:
        """Cari tombol kirim biru Instagram di kanan-bawah sheet komentar.

        Warna tombol terukur dari perangkat sungguhan adalah indigo
        (74, 93, 249); varian biru merek (0, 149, 246) juga diterima dengan
        toleransi ketat supaya biru pada isi video tidak ikut terhitung.
        Posisi memakai MEDIAN kluster dan kluster wajib padat (>= 800 piksel)
        agar piksel menyebar tidak menggeser titik tap.
        """
        width, height = image.size
        left = int(width * 0.72)
        right = int(width * 0.98)
        top = int(height * 0.62)
        bottom = int(height * 0.95)
        region = image.crop((left, top, right, bottom))
        pixels = region.load()
        region_w, region_h = region.size
        xs: list[int] = []
        ys: list[int] = []
        for yy in range(region_h):
            for xx in range(region_w):
                red, green, blue = pixels[xx, yy]
                indigo = abs(red - 74) < 40 and abs(green - 93) < 45 and blue > 219
                brand = red < 30 and abs(green - 149) < 25 and blue > 220
                if indigo or brand:
                    xs.append(xx)
                    ys.append(yy)
        if len(xs) < 800:
            return None
        xs.sort()
        ys.sort()
        return (left + xs[len(xs) // 2], top + ys[len(ys) // 2])

    def _stable_ig_blue(self) -> tuple[int, int] | None:
        """Posisi tombol kirim bila ada dan stabil di dua screenshot berurutan.

        Isi video yang kebetulan biru berubah-ubah antar frame; tombol yang
        sungguhan tidak berpindah lebih dari 40 piksel.
        """
        first = self._shot_image()
        position = self._find_ig_blue(first) if first is not None else None
        if position is None:
            return None
        time.sleep(1.2)
        second = self._shot_image()
        again = self._find_ig_blue(second) if second is not None else None
        if again is None:
            return None
        if abs(again[0] - position[0]) <= 40 and abs(again[1] - position[1]) <= 40:
            return again
        return None

    def _foreground_package(self) -> str:
        try:
            focus = str(self._adb("shell", "dumpsys", "window", check=False))
            match = re.search(r"mCurrentFocus=.*? (\S+)/", focus)
            return match.group(1) if match else ""
        except MobileAutomationError:
            return ""

    def _ensure_app_foreground(self, package: str) -> None:
        """Pastikan aplikasi sosial kembali di depan setelah kegagalan navigasi.

        Tanpa ini, satu ketukan BACK di feed bisa keluar ke home screen dan
        tap-tap koordinat berikutnya membuka aplikasi lain secara tidak sengaja.
        """
        if not package or self._foreground_package() == package:
            return
        self.add_log("Aplikasi tidak berada di depan; membuka ulang aplikasi.")
        self._adb(
            "shell", "am", "start",
            "-a", "android.intent.action.MAIN",
            "-p", package,
            timeout=30,
            check=False,
        )
        time.sleep(3)

    def _keyboard_shown(self) -> bool:
        state = str(self._adb("shell", "dumpsys", "input_method", check=False))
        return "mInputShown=true" in state

    def _dismiss_reply_mode(self) -> None:
        """Batalkan mode balasan bila kotak komentar terbuka sebagai 'Replying to'.

        Tap kotak teks pada sheet kadang mengenai tombol "Reply" komentar
        pertama; komentar automasi harus berdiri sendiri. Chip "Replying to"
        punya tombol tutup di ujung kanan barisnya — tekan bila terbaca di
        pohon UI, kalau tidak, tekan koordinat kanan baris chip.
        """
        try:
            nodes = self._nodes()
        except MobileAutomationError:
            return
        chip = next(
            (node for node in nodes if re.search(r"replying to|membalas", node.label, re.I)),
            None,
        )
        if chip is None:
            return
        close = next(
            (
                node
                for node in nodes
                if re.search(r"remove reply|cancel reply|batal(?:kan)? membalas", node.label, re.I)
                or (re.fullmatch(r"[✕×✖xX]", node.label.strip()) and node.clickable)
            ),
            None,
        )
        if close is not None:
            self._tap(close)
        else:
            # ✕ sering bukan node tersendiri di pohon UI; posisinya di kanan
            # baris chip.
            self._tap_xy(int(self.width * 0.9), (chip.bounds[1] + chip.bounds[3]) // 2)
        self.add_log("Mode balasan dibatalkan agar komentar berdiri sendiri.")
        time.sleep(1)

    def _reel_post_comment(self, text: str) -> bool:
        """Kirim komentar lewat sheet komentar + tombol kirim biru Instagram.

        Jalur pohon UI kadang sudah membuka sheet komentar sebelum gagal
        menemukan kotak teksnya, jadi kotak teks dicoba langsung di dua
        posisi (layout sheet berubah-ubah); kalau keyboard tetap tidak
        muncul, sheet dibuka lewat ikon komentar reel pada dua posisi rail
        yang pernah terukur (ikon bergeser antar reel mengikuti teks jumlah).
        """
        width, height = self.width, self.height
        field_positions = [
            # Titik yang jatuh di dalam kotak komentar pada tiga layout
            # terukur: pill "Add comment" feed reel (~0.901h), penampil Posts
            # (~0.909h), dan kotak pada sheet komentar (0.863-0.914h).
            # x=0.40 sengaja dipilih: pada bar aksi penampil Posts ia jatuh di
            # ruang kosong antar ikon, bukan di tombol Remix.
            (int(width * 0.40), int(height * 0.903)),
            (int(width * 0.40), int(height * 0.883)),
            (int(width * 0.40), int(height * 0.945)),
        ]
        icon_positions = [
            (int(width * 0.912), int(height * 0.281)),
            (int(width * 0.912), int(height * 0.297)),
        ]
        focused = False
        # None berarti sheet kemungkinan sudah terbuka: langsung kotak teks.
        for icon in (None, *icon_positions):
            if icon is not None:
                self._tap_xy(*icon)
                time.sleep(2.5)
            for field in (field_positions if icon is None else field_positions[:1]):
                self._tap_xy(*field)
                for _ in range(2):
                    time.sleep(1)
                    if self._keyboard_shown():
                        focused = True
                        break
                if focused:
                    break
            if focused:
                break
        if not focused:
            self.add_log("Kotak komentar reel tidak terbuka (keyboard tidak muncul).")
            self._adb("shell", "input", "keyevent", "KEYCODE_BACK", check=False)
            time.sleep(1)
            self._ensure_app_foreground(getattr(self, "_current_package", ""))
            return False
        self._dismiss_reply_mode()
        sent = self._input_text(text)
        if not sent:
            self.add_log("Komentar tidak memiliki karakter yang didukung input ADB.")
            self._adb("shell", "input", "keyevent", "KEYCODE_BACK", check=False)
            time.sleep(1)
            self._adb("shell", "input", "keyevent", "KEYCODE_BACK", check=False)
            return False
        time.sleep(1)
        # Kirim: cari panah biru Instagram (harus stabil di dua frame supaya
        # biru pada isi video tidak ikut terhitung); kalau deteksi warna
        # gagal, tekan koordinat fallback tempat tombol itu berada.
        submitted = False
        for attempt in range(3):
            target = self._stable_ig_blue()
            if target is None:
                target = (int(width * 0.887), int(height * 0.84))
                self.add_log(f"Percobaan kirim {attempt + 1}: tombol tidak terdeteksi stabil; pakai fallback {target}.")
            else:
                self.add_log(f"Percobaan kirim {attempt + 1}: tombol terdeteksi di {target}.")
            self._tap_xy(*target)
            time.sleep(3)
            if self._stable_ig_blue() is None:
                submitted = True
                self.add_log("Komentar reel terkirim: tombol kirim hilang setelah ditekan.")
                break
            self.add_log("Tombol kirim masih tampil; mencoba menekan lagi.")
        if not submitted:
            self._adb("shell", "input", "keyevent", "KEYCODE_ENTER", check=False)
            time.sleep(2)
            self.add_log("Komentar reel dicoba kirim via ENTER setelah tombol biru gagal.")
        if self._keyboard_shown():
            self._adb("shell", "input", "keyevent", "KEYCODE_BACK", check=False)
            time.sleep(1)
        self._adb("shell", "input", "keyevent", "KEYCODE_BACK", check=False)
        time.sleep(1)
        self._capture()
        return True

    def _nodes(self) -> list[UiNode]:
        # Hapus hasil dump lama lebih dulu: kalau `uiautomator dump` gagal
        # ("could not get idle state" di aplikasi yang terus beranimasi),
        # cat lama jangan sampai terbaca sebagai layar sekarang.
        self._adb("shell", "rm", "-f", "/sdcard/godam-window.xml", check=False)
        self._adb(
            "shell",
            "uiautomator",
            "dump",
            "/sdcard/godam-window.xml",
            timeout=25,
        )
        xml = str(self._adb("exec-out", "cat", "/sdcard/godam-window.xml", timeout=15))
        start = xml.find("<?xml")
        if start > 0:
            xml = xml[start:]
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as error:
            raise MobileAutomationError("Accessibility tree Android tidak dapat dibaca.") from error

        result: list[UiNode] = []
        for element in root.iter("node"):
            raw_bounds = element.attrib.get("bounds", "")
            numbers = [int(value) for value in re.findall(r"\d+", raw_bounds)]
            if len(numbers) != 4:
                continue
            result.append(
                UiNode(
                    text=element.attrib.get("text", ""),
                    description=element.attrib.get("content-desc", ""),
                    class_name=element.attrib.get("class", ""),
                    clickable=element.attrib.get("clickable") == "true",
                    bounds=(numbers[0], numbers[1], numbers[2], numbers[3]),
                )
            )
        return result

    @staticmethod
    def _matches(node: UiNode, patterns: Iterable[str]) -> bool:
        return any(re.search(pattern, node.label, re.IGNORECASE) for pattern in patterns)

    def _find(
        self,
        patterns: Iterable[str],
        *,
        class_pattern: str = "",
        attempts: int = 4,
        delay: float = 1.0,
    ) -> UiNode | None:
        for _ in range(attempts):
            if not self._running:
                return None
            try:
                for node in self._nodes():
                    if class_pattern and not re.search(class_pattern, node.class_name, re.I):
                        continue
                    if self._matches(node, patterns):
                        return node
            except MobileAutomationError:
                pass
            time.sleep(delay)
        return None

    def _tap(self, node: UiNode) -> None:
        x, y = node.center
        self._tap_xy(x, y)

    def _tap_xy(self, x: int, y: int) -> None:
        self._adb("shell", "input", "tap", str(x), str(y))

    def _tap_label(self, *patterns: str, attempts: int = 4, delay: float = 1.0) -> bool:
        node = self._find(patterns, attempts=attempts, delay=delay)
        if node is None:
            return False
        self._tap(node)
        time.sleep(1.2)
        self._capture()
        return True

    def _input_text(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
        normalized = re.sub(r"[^A-Za-z0-9 .,!?@#_+\-]", "", normalized).strip()
        payload = normalized.replace(" ", "%s")
        if payload:
            self._adb("shell", "input", "text", payload, timeout=30)
        return normalized

    def _tap_first_post(self) -> None:
        # Hanya label item media di grid (mis. "Reel by ... at row 1, column
        # 1"). Dua pengecualian penting: label statistik seperti "3,199posts"
        # juga memuat kata "post", dan tab "Reels" memuat kata "reel" —
        # keduanya pernah membuat tap mendarat di tempat yang salah. Karena
        # itu kandidat wajib node besar (sel grid, bukan tab setinggi ~144px)
        # dan berada di bawah 62% tinggi layar.
        min_height = max(200, int(self.height * 0.12))
        candidates = [
            node
            for node in self._nodes()
            if self._matches(node, (r"reel", r"photo", r"foto", r"video"))
            and node.bounds[1] > int(self.height * 0.62)
            and (node.bounds[3] - node.bounds[1]) > min_height
        ]
        if candidates:
            candidates.sort(key=lambda node: (node.bounds[1], node.bounds[0]))
            self._tap(candidates[0])
        else:
            # Fallback tetap ke area grid (bukan header profil).
            self._adb(
                "shell",
                "input",
                "tap",
                str(int(self.width * 0.25)),
                str(int(self.height * 0.78)),
            )
        time.sleep(2.5)
        self._capture()

    def _profile_still_visible(self) -> bool | None:
        """True bila layar masih halaman profil murni; False jika sudah pindah;
        None bila layar tidak dapat dibaca (umumnya karena video berputar).

        Saat postingan terbuka sebagai overlay, node profil di belakangnya
        (Message/Following) tetap ikut terbaca — jadi pembedanya adalah
        kehadiran tombol Like/Komentar yang hanya ada di halaman postingan.
        """
        try:
            nodes = self._nodes()
        except MobileAutomationError:
            return None
        for node in nodes:
            if re.search(r"^(like|suka|comment|komentar)$", node.label.strip(), re.IGNORECASE):
                return False
        labels = " | ".join(node.label.lower() for node in nodes)
        return "message" in labels and "following" in labels

    def _open_first_post(self, attempts: int = 3) -> None:
        """Buka postingan pertama dari grid profil, dengan verifikasi.

        Layout profil Instagram merender bertahap (bio, chip "Followed by",
        lalu grid) sehingga koordinat hasil dump bisa basi saat tap tiba.
        Setiap percobaan memeriksa dulu posisi sekarang, lalu men-tap dengan
        dump segar; berhenti begitu layar bukan lagi halaman profil.
        """
        for attempt in range(attempts):
            if not self._running:
                return
            if self._profile_still_visible() is not True:
                return
            self.add_log(f"Masih di halaman profil (cek {attempt + 1}); men-tap postingan pertama lagi.")
            self._tap_first_post()
            time.sleep(1.5)
        if self._profile_still_visible() is True:
            raise MobileAutomationError(
                "Tidak berhasil membuka postingan dari profil setelah beberapa percobaan."
            )

    def _tiktok_open_profile(self, target: str, package: str) -> None:
        """Buka profil TikTok lewat pencarian dalam aplikasi.

        Deep link web (tiktok.com/@user) pada varian aplikasi yang terpasang
        di farm sering diabaikan — intent berstatus ok tetapi yang terbuka
        adalah feed sembarang, sehingga aksi bisa mendarat di akun yang
        salah. Pencarian dalam aplikasi tervalidasi terbaca penuh oleh
        pohon UI: ikon Search → ketik username → tab Users → baris akun.
        """
        self._adb(
            "shell", "monkey", "-p", package,
            "-c", "android.intent.category.LAUNCHER", "1",
            check=False,
        )
        time.sleep(6)
        if not self._tap_label(r"^search$", attempts=3, delay=1.5):
            self._tap_xy(int(self.width * 0.92), int(self.height * 0.09))
        time.sleep(2.5)
        editor = self._find((r".*",), class_pattern="EditText", attempts=3)
        if editor is not None:
            self._tap(editor)
        else:
            self._tap_xy(int(self.width * 0.455), int(self.height * 0.085))
        sent = self._input_text(target)
        if not sent:
            raise MobileAutomationError("Username TikTok tidak dapat diketik di kotak pencarian.")
        time.sleep(1.5)
        if not self._tap_label(r"^search$", attempts=2, delay=1.5):
            self._adb("shell", "input", "keyevent", "KEYCODE_ENTER", check=False)
        time.sleep(4)
        if not self._tap_label(r"^users$", attempts=3, delay=1.5):
            self.add_log("Tab Users tidak ditemukan; mencoba memakai hasil Top.")
        time.sleep(3)
        nodes = self._nodes()
        needle = target.strip().lstrip("@").lower()
        row = next(
            (
                node
                for node in nodes
                if needle in node.label.lower() and node.clickable
                and (node.bounds[3] - node.bounds[1]) > 80
            ),
            None,
        )
        if row is None:
            # Baris akun kadang tidak clickable; tap node teksnya saja.
            row = next(
                (node for node in nodes if needle in node.label.lower() and node.bounds[1] > int(self.height * 0.15)),
                None,
            )
        if row is None:
            raise MobileAutomationError(
                f"Akun TikTok @{needle} tidak ditemukan pada hasil pencarian."
            )
        self._tap(row)
        time.sleep(4)
        self._capture()

    def _post_comment(self, text: str, spec: PlatformSpec) -> bool:
        if not self._tap_label(*spec.comment_patterns, attempts=3):
            self.add_log("Tombol komentar tidak ditemukan pada tampilan perangkat.")
            return False
        editor = self._find(spec.editor_patterns, class_pattern="EditText")
        if editor is None:
            editor = self._find((r".*",), class_pattern="EditText", attempts=2)
        if editor is None:
            self.add_log("Kotak komentar Android tidak ditemukan.")
            return False
        self._tap(editor)
        sent = self._input_text(text)
        if not sent:
            self.add_log("Komentar tidak memiliki karakter yang didukung input ADB.")
            return False
        if not self._tap_label(*spec.submit_patterns, attempts=4):
            self._adb("shell", "input", "keyevent", "KEYCODE_ENTER", check=False)
        time.sleep(2)
        self._capture()
        return True

    def _close_share_sheet(self) -> None:
        self._adb("shell", "input", "keyevent", "KEYCODE_BACK", check=False)
        time.sleep(1)
        self._capture()

    def _do_share(self, spec: PlatformSpec) -> bool:
        """Bagikan postingan lewat opsi aman (salin tautan / share langsung).

        Sheet share Instagram/TikTok juga menawarkan kontak untuk DM; kontak
        itu sengaja tidak pernah ditekan supaya automasi tidak mengirim pesan
        pribadi ke siapa pun.
        """
        if not self._tap_label(*spec.share_patterns, attempts=3):
            self.add_log("Tombol share tidak ditemukan pada tampilan perangkat.")
            return False
        option = self._find(spec.share_confirm_patterns, attempts=4)
        if option is None:
            self._close_share_sheet()
            self.add_log(_SHARE_SHEET_DELAY_NOTE)
            return False
        self._tap(option)
        time.sleep(1.5)
        self._capture()
        return True

    def _do_repost(self, spec: PlatformSpec) -> bool:
        """Repost postingan. X punya tombol langsung; TikTok/Facebook lewat sheet."""
        if spec.repost_via_share_sheet:
            if not self._tap_label(*spec.share_patterns, attempts=3):
                self.add_log("Tombol share tidak ditemukan; repost dibatalkan.")
                return False
            option = self._find(spec.repost_patterns, attempts=4)
            if option is None:
                self._close_share_sheet()
                self.add_log("Opsi repost tidak tersedia pada sheet share.")
                return False
            self._tap(option)
            time.sleep(1.5)
            self._capture()
            return True
        # "Undo repost" tidak cocok dengan pola ^repost$ sehingga repost yang
        # sudah ada tidak akan dibatalkan secara tidak sengaja.
        if not self._tap_label(*spec.repost_patterns, attempts=3):
            self.add_log("Sudah repost atau tombol repost tidak terlihat.")
            return False
        confirm = self._find(spec.repost_patterns, attempts=2, delay=0.8)
        if confirm is not None:
            self._tap(confirm)
            time.sleep(1.2)
        self._capture()
        return True

    def _run_comment(
        self,
        username: str,
        target: str,
        comment_count: int,
        max_posts: int,
        tone: str,
    ) -> None:
        self._run_engagement(
            "instagram", username, target, comment_count, max_posts, tone
        )

    def _run_engagement(
        self,
        platform: str,
        username: str,
        target: str,
        comment_count: int,
        max_posts: int,
        tone: str,
        actions: Iterable[str] | None = None,
    ) -> None:
        spec = PLATFORMS[platform]
        requested = normalize_actions(platform, actions)
        counters = dict.fromkeys(ACTION_ORDER, 0)
        try:
            package = self._prepare(spec.packages)
            self.status = "running"
            self.message = f"Menjalankan {spec.label} pada {self.device_serial}."
            self.add_log(f"Target eksekusi: STF / {self.device_serial}")
            self.add_log(f"Platform: {spec.label} · akun: {username or 'akun aktif'}")
            self.add_log(
                "Mode satu akun: hanya akun di perangkat ini yang digerakkan; "
                "tidak ada pergantian akun selama run."
            )
            self.add_log("Aksi per postingan: " + " → ".join(ACTION_LABELS[action] for action in requested))
            self._adb(
                "shell",
                "am",
                "start",
                "-W",
                "-a",
                "android.intent.action.VIEW",
                "-d",
                spec.profile_url.format(target=target.strip().lstrip("@")),
                "-p",
                package,
                timeout=45,
            )
            time.sleep(6)
            self._capture()
            if platform == "tiktok":
                # TikTok: deep link web tidak andal membuka profil, jadi
                # navigasi memakai pencarian dalam aplikasi lalu video
                # pertama di grid profil.
                self._tiktok_open_profile(target.strip().lstrip("@"), package)
                self._tap_first_post()
                time.sleep(3)
                self._capture()
            elif platform == "instagram":
                # Buka postingan pertama dengan verifikasi anti-layout-race,
                # lalu satu tap tengah berpindah ke feed Reels layar penuh
                # yang punya rail aksi (like/komentar/share).
                self._open_first_post()
                time.sleep(1)
                # Bila ponsel mendarat di akun pribadi/kosong (mis. lewat
                # konten yang dikolaborasi), like/komentar mustahil dilakukan;
                # beri tahu operator dengan jelas.
                try:
                    nodes = self._nodes()
                    joined = " | ".join(node.label for node in nodes)
                    if re.search(r"bersifat pribadi|this account is private", joined, re.IGNORECASE):
                        self.add_log(
                            "Konten yang terbuka bersifat pribadi/kosong; "
                            "like dan komentar pada postingan ini dilewati."
                        )
                except MobileAutomationError:
                    pass
                self._adb(
                    "shell", "input", "tap",
                    str(self.width // 2), str(self.height // 2),
                    check=False,
                )
                time.sleep(2.5)
                self._capture()
            else:
                self._tap_first_post()

            from comment_ai import generate_comments
            from tasks import generate_comments_from_bank

            processed = 0
            for post_index in range(max_posts):
                if not self._running:
                    break
                processed += 1
                self.add_log(f"Memproses postingan {post_index + 1}/{max_posts}.")
                for action in requested:
                    if not self._running:
                        break
                    if action == "like":
                        if self._tap_label(*spec.like_patterns, attempts=2):
                            counters["like"] += 1
                            self.add_log(f"Like {spec.label} dikirim dari perangkat Android.")
                        elif platform == "instagram" and self._reel_like():
                            counters["like"] += 1
                            self.add_log("Like reel terkirim dan terverifikasi dari warna hati.")
                        else:
                            self.add_log("Like tidak terkonfirmasi pada tampilan perangkat.")
                    elif action == "comment":
                        if comment_count < 1:
                            self.add_log("Jumlah komentar 0; aksi komentar dilewati.")
                            continue
                        comments = asyncio.run(
                            generate_comments(
                                f"Postingan {spec.label} @{target}",
                                comment_count,
                                tone,
                                local_fallback=generate_comments_from_bank,
                            )
                        )
                        for comment in comments:
                            if not self._running:
                                break
                            if self._post_comment(comment, spec):
                                counters["comment"] += 1
                                self.add_log(f"Komentar Android terkirim: {comment[:80]}")
                            elif platform == "instagram" and self._reel_post_comment(comment):
                                counters["comment"] += 1
                                self.add_log(f"Komentar reel terkirim: {comment[:80]}")
                            else:
                                self.add_log("Komentar gagal dikirim pada postingan ini.")
                            time.sleep(1.5)
                    elif action == "share":
                        if self._do_share(spec):
                            counters["share"] += 1
                            self.add_log(f"Share {spec.label} selesai (opsi aman: tautan/share langsung).")
                        elif platform == "instagram":
                            self.add_log(
                                "Share pada feed reel dilewati: sheet share tidak dapat dibaca "
                                "aman tanpa pohon UI, dan automasi tidak menekan kontak/DM."
                            )
                        else:
                            self.add_log("Tombol share tidak ditemukan pada tampilan perangkat.")
                    elif action == "repost":
                        if self._do_repost(spec):
                            counters["repost"] += 1
                            self.add_log(f"Repost {spec.label} dikirim.")

                if post_index + 1 < max_posts:
                    self._adb(
                        "shell",
                        "input",
                        "swipe",
                        str(self.width // 2),
                        str(int(self.height * 0.82)),
                        str(self.width // 2),
                        str(int(self.height * 0.28)),
                        "550",
                    )
                    time.sleep(2)
                    self._capture()

            if self._running:
                self.status = "completed"
                self.message = f"Otomasi {spec.label} selesai di perangkat STF."
                self.result = {
                    "comments_posted": counters["comment"],
                    "likes_sent": counters["like"],
                    "shares_sent": counters["share"],
                    "reposts_sent": counters["repost"],
                    "posts_processed": processed,
                    "actions": requested,
                    "mode": "single-account",
                    "account": username or "akun-aktif",
                    "platform": platform,
                    "device_serial": self.device_serial,
                    "execution_target": "stf",
                }
        except (MobileAutomationError, HTTPException) as error:
            self.status = "error"
            detail = getattr(error, "detail", str(error))
            self.message = str(detail)
            self.add_log(f"Gagal: {detail}")
        except Exception as error:
            logger.exception("Eksekusi mobile gagal")
            self.status = "error"
            self.message = "Eksekusi Android gagal. Periksa log backend."
            self.add_log(f"Gagal: {error}")
        finally:
            self._running = False
            self._release()

    def _run_upload(self, username: str, berkas: str, caption: str) -> None:
        remote_path = f"/sdcard/Movies/Godam/{Path(berkas).name}"
        try:
            package = self._prepare((INSTAGRAM_PACKAGE,))
            self.status = "running"
            self.message = f"Mengirim video ke {self.device_serial}."
            self.add_log(f"Target eksekusi: STF / {self.device_serial}")
            self._adb("shell", "mkdir", "-p", "/sdcard/Movies/Godam")
            self._adb("push", berkas, remote_path, timeout=600)
            self.add_log("Video disalin ke galeri perangkat.")
            self._adb(
                "shell",
                "am",
                "broadcast",
                "-a",
                "android.intent.action.MEDIA_SCANNER_SCAN_FILE",
                "-d",
                f"file://{remote_path}",
                check=False,
            )
            time.sleep(2)
            query = str(
                self._adb(
                    "shell",
                    "content",
                    "query",
                    "--uri",
                    "content://media/external/video/media",
                    "--projection",
                    "_id:_data",
                    "--where",
                    f"_data='{remote_path}'",
                    check=False,
                )
            )
            ids = re.findall(r"_id=(\d+)", query)
            stream = f"content://media/external/video/media/{ids[-1]}" if ids else f"file://{remote_path}"
            self._adb(
                "shell",
                "am",
                "start",
                "-W",
                "-a",
                "android.intent.action.SEND",
                "-t",
                "video/mp4",
                "--eu",
                "android.intent.extra.STREAM",
                stream,
                "--grant-read-uri-permission",
                "-p",
                package,
                timeout=45,
            )
            time.sleep(4)
            self._capture()
            for _ in range(2):
                if self._tap_label(r"^next$", r"^selanjutnya$", r"lanjut", attempts=5):
                    time.sleep(2)
            if caption.strip():
                editor = self._find(
                    (r"caption", r"keterangan", r"write a caption"),
                    class_pattern="EditText",
                    attempts=5,
                )
                if editor:
                    self._tap(editor)
                    normalized = self._input_text(caption)
                    if normalized != caption.strip():
                        self.add_log("Caption dinormalisasi agar kompatibel dengan input ADB.")
            if not self._tap_label(r"^share$", r"^bagikan$", r"publish", attempts=6):
                raise MobileAutomationError("Tombol Bagikan Instagram tidak ditemukan.")
            time.sleep(6)
            self._capture()
            if self._running:
                self.status = "completed"
                self.message = "Video diproses oleh Instagram di perangkat STF."
                self.result = {
                    "status": "uploaded",
                    "device_serial": self.device_serial,
                    "execution_target": "stf",
                    "username": username,
                }
        except (MobileAutomationError, HTTPException) as error:
            self.status = "error"
            detail = getattr(error, "detail", str(error))
            self.message = str(detail)
            self.add_log(f"Gagal: {detail}")
        except Exception as error:
            logger.exception("Unggah mobile gagal")
            self.status = "error"
            self.message = "Unggah Android gagal. Periksa log backend."
            self.add_log(f"Gagal: {error}")
        finally:
            self._running = False
            self._release()
