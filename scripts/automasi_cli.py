"""CLI automasi satu akun — auto like & auto comment Instagram/TikTok.

Semua perintah mengarah ke Control Center lokal (http://localhost:3000/device-farm
menggunakan backend http://localhost:8000).

Contoh:
    python scripts/automasi_cli.py status
    python scripts/automasi_cli.py devices
    python scripts/automasi_cli.py run --platform instagram --device R5CT10BPZAM \\
        --target tvrakyat.official --actions like,comment --comments 1 --posts 2 --watch
    python scripts/automasi_cli.py run --platform tiktok --device 344831514a373598 \\
        --target tvrakyatofficial --actions like,comment --watch
    python scripts/automasi_cli.py runs 5
    python scripts/automasi_cli.py watch RUN_ID
    python scripts/automasi_cli.py stop RUN_ID
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

BACKEND = "http://localhost:8000"
TERMINAL = {"completed", "error", "stopped", "needs_review"}


def api(path: str, payload: dict | None = None, method: str = "GET") -> dict:
    request = urllib.request.Request(
        BACKEND + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace")
        try:
            message = json.loads(detail).get("detail", detail)
        except json.JSONDecodeError:
            message = detail[:200]
        raise SystemExit(f"HTTP {error.code}: {message}")
    except urllib.error.URLError as error:
        raise SystemExit(f"Backend tidak merespons: {error.reason}")


def cmd_status(_: argparse.Namespace) -> None:
    health = api("/health")
    print("Backend:", health.get("status"))
    devices = api("/api/device-farm/devices").get("devices", [])
    ready = [d for d in devices if d.get("present") and d.get("ready")]
    print(f"Perangkat STF: {len(ready)} siap / {len(devices)} terdaftar")
    for device in ready:
        serial = device["serial"]
        net = "ONLINE" if _ping_via_cli(serial) else "offline"
        print(f"  {serial} | {device.get('marketName') or device.get('model')} | internet: {net} | dipakai: {bool(device.get('using'))}")
    if not ready:
        print("  Tidak ada perangkat siap. Cek kabel USB / hub / `adb devices`.")


def _ping_via_cli(serial: str) -> bool:
    import subprocess
    adb = r"C:\Users\LENOVO\Downloads\platform-tools-latest-windows\platform-tools\adb.exe"
    try:
        result = subprocess.run(
            [adb, "-s", serial, "shell", "ping -c 1 -W 2 8.8.8.8"],
            capture_output=True, timeout=12,
        )
        return result.returncode == 0
    except Exception:
        return False


def cmd_devices(_: argparse.Namespace) -> None:
    cmd_status(_)


def cmd_run(args: argparse.Namespace) -> None:
    actions = [a.strip() for a in args.actions.split(",") if a.strip()]
    payload = {
        "platform": args.platform,
        "device_serial": args.device,
        "target": args.target,
        "username": args.account,
        "actions": actions,
        "comment_count": args.comments,
        "max_posts": args.posts,
        "tone": args.tone,
    }
    started = api("/api/farm-automation/single-account/runs", payload, method="POST")
    run_id = started["run_id"]
    print(f"Run dimulai: {run_id} | {started['platform']} | perangkat {started['devices'][0]}")
    print(f"Aksi: {', '.join(started['actions'])} | target: {payload['target']}")
    if not args.watch:
        print(f"Pantau: python scripts/automasi_cli.py watch {run_id}")
        return
    watch_run(run_id)


def watch_run(run_id: str) -> None:
    printed = 0
    while True:
        run = api(f"/api/farm-automation/runs/{run_id}")
        for job in run.get("jobs", []):
            logs = job.get("logs") or []
            for line in logs[printed:]:
                print("  |", line)
            printed = len(logs)
        if run.get("status") != "running":
            result = (run.get("jobs") or [{}])[0].get("result") or {}
            print("\nSelesai:", run.get("status"), "|", run.get("jobs", [{}])[0].get("message", ""))
            for key in ("likes_sent", "comments_posted", "shares_sent", "reposts_sent", "posts_processed"):
                if key in result:
                    print(f"  {key}: {result[key]}")
            return
        time.sleep(4)


def cmd_watch(args: argparse.Namespace) -> None:
    watch_run(args.run_id)


def cmd_runs(args: argparse.Namespace) -> None:
    runs = api("/api/farm-automation/runs").get("runs", [])[: args.limit]
    if not runs:
        print("Belum ada run.")
        return
    for run in runs:
        job = (run.get("jobs") or [{}])[0]
        result = job.get("result") or {}
        ringkas = " ".join(
            f"{key}={result[key]}" for key in ("likes_sent", "comments_posted", "shares_sent", "reposts_sent")
            if key in result
        )
        print(f"{run['run_id'][:8]} | {run.get('platform', '?'):9} | {run.get('target', '?'):20} | "
              f"{run['status']:12} | {job.get('outcome', '-'):22} {ringkas}")


def cmd_stop(args: argparse.Namespace) -> None:
    run = api(f"/api/farm-automation/runs/{args.run_id}/stop", {}, method="POST")
    print("Status:", run.get("status"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Automasi satu akun Godam (like/komen/share/repost).")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Kesehatan backend + daftar perangkat").set_defaults(func=cmd_status)
    sub.add_parser("devices", help="Alias dari status").set_defaults(func=cmd_devices)

    run = sub.add_parser("run", help="Mulai automasi satu akun")
    run.add_argument("--platform", required=True, choices=["instagram", "tiktok", "x", "facebook", "threads"])
    run.add_argument("--device", required=True, help="Serial perangkat (lihat: status)")
    run.add_argument("--target", required=True, help="Username tujuan tanpa @")
    run.add_argument("--account", default="akun-aktif", help="Label akun di perangkat")
    run.add_argument("--actions", default="like,comment", help="Kombinasi: like,comment,share,repost")
    run.add_argument("--comments", type=int, default=1, help="Komentar per postingan (1-20)")
    run.add_argument("--posts", type=int, default=1, help="Jumlah postingan (1-25)")
    run.add_argument("--tone", default="positif", choices=["positif", "netral", "negatif"])
    run.add_argument("--watch", action="store_true", help="Pantau log secara langsung")
    run.set_defaults(func=cmd_run)

    watch = sub.add_parser("watch", help="Pantau run berjalan")
    watch.add_argument("run_id")
    watch.set_defaults(func=cmd_watch)

    runs = sub.add_parser("runs", help="Riwayat run terakhir")
    runs.add_argument("limit", nargs="?", type=int, default=10)
    runs.set_defaults(func=cmd_runs)

    stop = sub.add_parser("stop", help="Hentikan run")
    stop.add_argument("run_id")
    stop.set_defaults(func=cmd_stop)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
