"""Sambungkan seluruh perangkat farm ke WiFi "Admin Medsos LT2".

Dijalankan dari PC host (yang punya akses adb ke semua perangkat):
    python scripts/sambungkan_wifi_semua.py

Proses per perangkat:
1. Lewati bila perangkat sudah online (ping 8.8.8.8).
2. Buka Setelan Wi-Fi, kunci orientasi portrait (koordinat dump = koordinat tap).
3. Bila jaringan sudah tersimpan/terlihat, tap barisnya. Bila belum, buka
   "Add network": isi SSID, pastikan keamanan WPA, isi password,
   matikan "Hidden network" bila menyala, lalu Save.
4. Tunggu hingga mendapat internet (maks 60 detik), laporkan hasil.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ADB = r"C:\Users\LENOVO\Downloads\platform-tools-latest-windows\platform-tools\adb.exe"
SSID = "Admin Medsos LT2"
SSID_TYPED = SSID.replace(" ", "%s")
PASSWORD = "bersama@PRI123"


def adb(*args: str, timeout: int = 25) -> str:
    result = subprocess.run(
        [ADB, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.stdout.strip()


def shell(serial: str, command: str, timeout: int = 20) -> str:
    return adb("-s", serial, "shell", command, timeout=timeout)


def online(serial: str) -> bool:
    output = shell(serial, "ping -c 1 -W 2 8.8.8.8 2>&1 | tail -1", timeout=15)
    return "1 received" in output or "1 packets received" in output or "time=" in output


def center(bounds: str) -> tuple[int, int] | None:
    numbers = [int(v) for v in re.findall(r"\d+", bounds)]
    if len(numbers) != 4:
        return None
    return (numbers[0] + numbers[2]) // 2, (numbers[1] + numbers[3]) // 2


def dump(serial: str) -> ET.Element | None:
    shell(serial, "uiautomator dump /sdcard/gw-wifi.xml", timeout=25)
    xml_text = adb("-s", serial, "exec-out", "cat", "/sdcard/gw-wifi.xml", timeout=15)
    start = xml_text.find("<?xml")
    if start < 0:
        return None
    try:
        return ET.fromstring(xml_text[start:])
    except ET.ParseError:
        return None


def tap_label(serial: str, root: ET.Element, pattern: str) -> bool:
    for node in root.iter("node"):
        label = (node.attrib.get("text", "") + " " + node.attrib.get("content-desc", "")).strip()
        if re.search(pattern, label, re.IGNORECASE):
            point = center(node.attrib.get("bounds", ""))
            if point:
                shell(serial, f"input tap {point[0]} {point[1]}")
                return True
    return False


def network_row(serial: str) -> bool:
    """Bila jaringan target sudah tampil di halaman Wi-Fi, tap untuk menyambung."""
    root = dump(serial)
    if root is None:
        return False
    for node in root.iter("node"):
        label = (node.attrib.get("text", "") + " " + node.attrib.get("content-desc", "")).strip()
        if SSID.lower() in label.lower():
            point = center(node.attrib.get("bounds", ""))
            if point:
                shell(serial, f"input tap {point[0]} {point[1]}")
                return True
    return False


def add_network(serial: str) -> None:
    root = dump(serial)
    if root is None:
        raise RuntimeError("layar tidak dapat dibaca")
    if not tap_label(serial, root, r"^add network$|^tambahkan jaringan$"):
        tap_fraction(serial, 0.23, 0.53)
    time.sleep(2.5)

    root = dump(serial)
    if root is None:
        raise RuntimeError("dialog Add network tidak terbaca")
    fields = find_edittexts(root)
    if not fields:
        raise RuntimeError("dialog Add network tidak ditemukan")
    # Field pertama = SSID.
    shell(serial, f"input tap {fields[0][0]} {fields[0][1]}")
    time.sleep(1)
    shell(serial, f"input text '{SSID_TYPED}'")
    time.sleep(1)

    # Keamanan: pastikan ber-WPA (bila bukan, buka pilihannya dan pilih WPA).
    root = dump(serial)
    labels = " | ".join(
        (n.attrib.get("text", "") + " " + n.attrib.get("content-desc", ""))
        for n in root.iter("node")
    ) if root is not None else ""
    if "WPA" not in labels:
        tap_label(serial, root, r"^security$|^keamanan$")
        time.sleep(1.5)
        root = dump(serial)
        if root is not None:
            tap_label(serial, root, r"WPA")
        time.sleep(1.5)

    # Field kedua (bila ada) = password.
    root = dump(serial)
    fields = find_edittexts(root) if root is not None else []
    if len(fields) >= 2:
        shell(serial, f"input tap {fields[1][0]} {fields[1][1]}")
        time.sleep(1)
        shell(serial, f"input text '{PASSWORD}'")
        time.sleep(1)

    root = dump(serial)
    if root is not None:
        # Matikan "Hidden network" bila switch-nya menyala.
        for node in root.iter("node"):
            label = (node.attrib.get("text", "")).strip()
            if re.search(r"hidden network|jaringan tersembunyi", label, re.IGNORECASE):
                point = center(node.attrib.get("bounds", ""))
                if point:
                    shell(serial, f"input tap {int(1080 * 0.88)} {point[1]}")
                    time.sleep(1)
                break
        shell(serial, "input keyevent 111")  # tutup keyboard
        time.sleep(1.5)
        root = dump(serial)
        if root is not None and not tap_label(serial, root, r"^save$|^simpan$|^ok$"):
            shell(serial, "input swipe 540 1500 540 700 400")
            time.sleep(1.5)
            root = dump(serial)
            if root is not None:
                tap_label(serial, root, r"^save$|^simpan$|^ok$")
    time.sleep(3)


def tap_fraction(serial: str, fx: float, fy: float) -> None:
    shell(serial, f"input tap {int(1080 * fx)} {int(1920 * fy)}")


def find_edittexts(root: ET.Element) -> list[tuple[int, int]]:
    fields = []
    for node in root.iter("node"):
        if "EditText" in node.attrib.get("class", ""):
            point = center(node.attrib.get("bounds", ""))
            if point:
                fields.append(point)
    return fields


def provision(serial: str) -> bool:
    print(f"[{serial}] membuka Setelan Wi-Fi...")
    shell(serial, "settings put system accelerometer_rotation 0")
    shell(serial, "settings put system user_rotation 0")
    shell(serial, "cmd window user-rotation lock 0 0")
    shell(serial, "am start -a android.settings.WIFI_SETTINGS")
    time.sleep(5)

    if network_row(serial):
        print(f"[{serial}] jaringan '{SSID}' sudah ada; men-tap untuk menyambung.")
    else:
        print(f"[{serial}] menambahkan jaringan baru...")
        add_network(serial)

    for attempt in range(6):
        time.sleep(10)
        if online(serial):
            print(f"[{serial}] TERHUBUNG ke internet via '{SSID}' ✓")
            return True
        print(f"[{serial}] menunggu IP/DHCP... ({(attempt + 1) * 10}s)")
    print(f"[{serial}] Wi-Fi tersimpan tetapi internet belum jalan (router menolak?).")
    return False


def main() -> None:
    devices = [
        line.split("\t")[0]
        for line in adb("devices").splitlines()[1:]
        if "\tdevice" in line
    ]
    if len(sys.argv) > 1:
        devices = [s for s in devices if s in sys.argv[1:]]
    if not devices:
        print("Tidak ada perangkat adb.")
        return
    hasil: dict[str, bool] = {}
    for serial in devices:
        if online(serial):
            print(f"[{serial}] sudah online; lewati.")
            hasil[serial] = True
            continue
        try:
            hasil[serial] = provision(serial)
        except Exception as error:  # lanjut ke perangkat berikutnya
            print(f"[{serial}] gagal: {error}")
            hasil[serial] = False
    print("\n=== RINGKASAN ===")
    for serial, ok in hasil.items():
        print(f"{serial}: {'ONLINE' if ok else 'BELUM ONLINE'}")
    print(f"Total online: {sum(hasil.values())}/{len(hasil)}")


if __name__ == "__main__":
    main()
