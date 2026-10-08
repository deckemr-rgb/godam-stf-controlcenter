"""Integrasi DeviceFarmer STF untuk portal Godam.

Token STF hanya digunakan di server. Browser berbicara dengan router ini memakai
token sesi Godam, sehingga access token STF tidak pernah masuk bundle frontend.
"""

from __future__ import annotations

import io
import os
import re
import subprocess
import threading
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field
from PIL import Image

from auth_api import baca_token


router = APIRouter(prefix="/api/device-farm", tags=["device-farm"])

STF_URL = os.getenv("STF_URL", "http://stf-proxy:7100").strip().rstrip("/")
STF_PUBLIC_URL = os.getenv("STF_PUBLIC_URL", "http://localhost:7100").strip().rstrip("/")
STF_TOKEN = os.getenv("STF_TOKEN", "").strip()
STF_TIMEOUT_SECONDS = float(os.getenv("STF_TIMEOUT_SECONDS", "15"))
STF_VERIFY_SSL = os.getenv("STF_VERIFY_SSL", "true").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
STF_REQUIRE_GODAM_AUTH = os.getenv("STF_REQUIRE_GODAM_AUTH", "true").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
STF_ADB_HOST = os.getenv("STF_ADB_HOST", "stf-adb").strip()
STF_ADB_PORT = int(os.getenv("STF_ADB_PORT", "5037"))
SCREENSHOT_CONCURRENCY = max(1, int(os.getenv("STF_SCREENSHOT_CONCURRENCY", "2")))
_SCREENSHOT_SLOTS = threading.BoundedSemaphore(SCREENSHOT_CONCURRENCY)

SERIAL_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
DEVICE_FIELDS = ",".join(
    (
        "serial",
        "present",
        "ready",
        "using",
        "usable",
        "owner",
        "manufacturer",
        "model",
        "marketName",
        "version",
        "sdk",
        "battery",
        "display",
        "network",
        "provider",
    )
)


class ReservationBody(BaseModel):
    timeout_seconds: int = Field(default=1800, ge=60, le=86400)


def _require_godam_session(authorization: str = Header(default="")) -> dict[str, Any] | None:
    if not STF_REQUIRE_GODAM_AUTH:
        return None
    token = authorization.removeprefix("Bearer ").strip()
    session = baca_token(token)
    if not session:
        raise HTTPException(status_code=401, detail="Masuk ke Godam untuk mengelola device farm.")
    return session


def _serial(value: str) -> str:
    if not SERIAL_PATTERN.fullmatch(value):
        raise HTTPException(status_code=422, detail="Serial perangkat tidak valid.")
    return quote(value, safe="")


def _configuration_required() -> None:
    if not STF_URL or not STF_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Device farm belum dikonfigurasi. Isi STF_URL dan STF_TOKEN di server.",
        )


def _request(
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    params: dict[str, str] | None = None,
) -> dict[str, Any]:
    _configuration_required()
    headers = {"Authorization": f"Bearer {STF_TOKEN}", "Accept": "application/json"}
    try:
        with httpx.Client(
            timeout=httpx.Timeout(STF_TIMEOUT_SECONDS, connect=min(STF_TIMEOUT_SECONDS, 5.0)),
            follow_redirects=True,
            verify=STF_VERIFY_SSL,
        ) as client:
            response = client.request(
                method,
                f"{STF_URL}{path}",
                headers=headers,
                json=json,
                params=params,
            )
    except httpx.TimeoutException as error:
        raise HTTPException(status_code=504, detail="STF tidak merespons sebelum timeout.") from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=503, detail="STF tidak dapat dijangkau.") from error

    if response.status_code >= 400:
        detail = "Permintaan ke STF gagal."
        try:
            payload = response.json()
            detail = str(payload.get("description") or payload.get("detail") or detail)
        except ValueError:
            if response.text.strip():
                detail = response.text.strip()[:300]
        upstream_status = response.status_code if response.status_code < 500 else 502
        raise HTTPException(status_code=upstream_status, detail=detail)

    if response.status_code == 204 or not response.content:
        return {"success": True}
    try:
        return response.json()
    except ValueError as error:
        raise HTTPException(status_code=502, detail="STF mengembalikan respons yang tidak valid.") from error


@router.get("/config")
def config() -> dict[str, Any]:
    return {
        "configured": bool(STF_URL and STF_TOKEN),
        "public_url": STF_PUBLIC_URL,
        "godam_auth_required": STF_REQUIRE_GODAM_AUTH,
    }


@router.get("/status")
def status(_: dict[str, Any] | None = Depends(_require_godam_session)) -> dict[str, Any]:
    payload = _request("GET", "/api/v1/user")
    return {
        "status": "ok",
        "stf_url": STF_PUBLIC_URL,
        "user": payload.get("user", {}),
    }


@router.get("/devices")
def devices(_: dict[str, Any] | None = Depends(_require_godam_session)) -> dict[str, Any]:
    return _request("GET", "/api/v1/devices", params={"fields": DEVICE_FIELDS})


@router.get("/reservations")
def reservations(_: dict[str, Any] | None = Depends(_require_godam_session)) -> dict[str, Any]:
    return _request("GET", "/api/v1/user/devices", params={"fields": DEVICE_FIELDS})


@router.get("/diagnostics")
def diagnostics(_: dict[str, Any] | None = Depends(_require_godam_session)) -> dict[str, Any]:
    """Read-only comparison of STF inventory and ADB; no reserve or UI input."""
    issues = []
    inventory = []
    stf_ok = adb_ok = False
    try:
        inventory = _request("GET", "/api/v1/devices", params={"fields": DEVICE_FIELDS}).get("devices", [])
        stf_ok = True
    except HTTPException as error:
        issues.append(str(error.detail))
    adb_states = {}
    try:
        result = subprocess.run(
            ["adb", "-H", STF_ADB_HOST, "-P", str(STF_ADB_PORT), "devices"],
            capture_output=True, text=True, timeout=8, check=False,
        )
        adb_ok = result.returncode == 0
        if not adb_ok:
            issues.append("ADB host tidak dapat dijangkau.")
        else:
            for line in result.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 2 and parts[1] in {"device", "offline", "unauthorized", "recovery", "bootloader", "sideload"}:
                    adb_states[parts[0]] = parts[1]
    except (OSError, subprocess.TimeoutExpired):
        issues.append("Pemeriksaan ADB gagal atau timeout.")
    indexed = {item["serial"]: item for item in inventory}
    rows = []
    for serial in sorted(set(indexed) | set(adb_states)):
        item = indexed.get(serial, {})
        state = adb_states.get(serial, "missing" if adb_ok else "unknown")
        notes = []
        if state != "device":
            notes.append(f"ADB: {state}")
        if not item.get("present"):
            notes.append("Tidak terdeteksi di STF")
        elif not item.get("ready"):
            notes.append("Provider STF belum siap")
        if item.get("using"):
            notes.append("Sedang direservasi; jangan ambil alih sesi aktif")
        if item.get("usable") is False:
            notes.append("STF menandai perangkat tidak dapat dipakai")
        rows.append({"serial": serial, "adb": state, "ready": bool(item.get("present") and item.get("ready")),
                     "busy": bool(item.get("using")), "issues": notes})
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "stf_ok": stf_ok, "adb_ok": adb_ok,
            "issues": issues, "devices": rows, "read_only": True,
            "scope": "Koneksi STF/ADB saja; tidak memverifikasi login, internet aplikasi, atau keberhasilan tugas."}


@router.get("/devices/{serial}")
def device(serial: str, _: dict[str, Any] | None = Depends(_require_godam_session)) -> dict[str, Any]:
    return _request(
        "GET",
        f"/api/v1/devices/{_serial(serial)}",
        params={"fields": DEVICE_FIELDS},
    )


@router.get("/devices/{serial}/screenshot")
def screenshot(
    serial: str,
    _: dict[str, Any] | None = Depends(_require_godam_session),
) -> Response:
    """Ambil thumbnail layar langsung dari ADB utama STF."""
    _serial(serial)
    command = [
        "adb", "-H", STF_ADB_HOST, "-P", str(STF_ADB_PORT),
        "-s", serial, "exec-out", "screencap", "-p",
    ]
    if not _SCREENSHOT_SLOTS.acquire(timeout=0.5):
        raise HTTPException(status_code=429, detail="Antrean screenshot penuh; coba pada refresh berikutnya.",
                            headers={"Retry-After": "3"})
    try:
        result = subprocess.run(
            command, check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=12,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as error:
        raise HTTPException(status_code=503, detail="Screenshot perangkat tidak tersedia.") from error
    finally:
        _SCREENSHOT_SLOTS.release()
    if result.returncode or not result.stdout.startswith(b"\x89PNG"):
        detail = result.stderr.decode("utf-8", "replace").strip() or "Perangkat belum siap."
        raise HTTPException(status_code=503, detail=detail[:200])
    try:
        with Image.open(io.BytesIO(result.stdout)) as image:
            image.thumbnail((360, 720))
            output = io.BytesIO()
            image.convert("RGB").save(output, format="JPEG", quality=58, optimize=True)
            content = output.getvalue()
    except OSError as error:
        raise HTTPException(status_code=502, detail="Frame Android tidak dapat diproses.") from error
    return Response(
        content=content,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@router.post("/devices/{serial}/reserve")
def reserve(
    serial: str,
    body: ReservationBody,
    _: dict[str, Any] | None = Depends(_require_godam_session),
) -> dict[str, Any]:
    _serial(serial)
    return _request(
        "POST",
        "/api/v1/user/devices",
        json={"serial": serial, "timeout": body.timeout_seconds * 1000},
    )


@router.delete("/devices/{serial}/reserve")
def release(serial: str, _: dict[str, Any] | None = Depends(_require_godam_session)) -> dict[str, Any]:
    return _request("DELETE", f"/api/v1/user/devices/{_serial(serial)}")


@router.post("/devices/{serial}/remote-connect")
def remote_connect(
    serial: str,
    _: dict[str, Any] | None = Depends(_require_godam_session),
) -> dict[str, Any]:
    return _request("POST", f"/api/v1/user/devices/{_serial(serial)}/remoteConnect")


@router.delete("/devices/{serial}/remote-connect")
def remote_disconnect(
    serial: str,
    _: dict[str, Any] | None = Depends(_require_godam_session),
) -> dict[str, Any]:
    return _request("DELETE", f"/api/v1/user/devices/{_serial(serial)}/remoteConnect")
