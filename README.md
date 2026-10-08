# Godam STF Control Center

Control Center lokal untuk menjalankan automation Godam melalui engine Android
[DeviceFarmer STF](https://github.com/DeviceFarmer/stf). STF menangani inventaris,
reservasi, layar, ADB, dan lifecycle perangkat; Godam menangani workflow sosial,
parameter pekerjaan, fan-out ke banyak perangkat, log, dan status gabungan.

## Fitur

- satu dashboard ringan bergaya phone farm untuk 16 perangkat;
- live screenshot terkompresi, pencarian, filter, dan multi-select;
- fan-out automation ke perangkat terpilih secara paralel;
- Instagram, TikTok, X, Facebook, dan Threads;
- like dan comment melalui aplikasi native Android;
- status run per perangkat, stop run, dan pelepasan reservasi otomatis;
- ML dry-run untuk scoring like/comment/share, ranking akun, dan rencana switch;
- online feedback learning tanpa mengeksekusi aksi sosial;
- STF penuh tetap tersedia untuk remote control dan diagnostik lanjutan;
- instalasi localhost Windows satu perintah, dengan source berada di disk D.

## Arsitektur

```text
Control Center (Next.js)
        |
        v
Godam API + Farm Orchestrator (FastAPI)
        |                         |
        | STF REST/reservation    | ADB action + screenshot
        v                         v
DeviceFarmer STF provider ---> Windows ADB :5037 ---> 16 Android devices
```

STF adalah main engine. Godam bukan aplikasi terpisah di samping STF: halaman
utama, pemilihan perangkat, dan pekerjaan sosial menggunakan inventaris serta
reservasi STF yang sama.

## Jalankan di Windows

```powershell
Set-Location D:\GodamSTF-ControlCenter\app
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\start-local.ps1
```

Buka `http://localhost:3000`. Instruksi lengkap ada di
[LOCALHOST.md](LOCALHOST.md).

## Endpoint integrasi utama

| Method | Endpoint | Fungsi |
| --- | --- | --- |
| `GET` | `/api/device-farm/devices` | Inventaris STF |
| `GET` | `/api/device-farm/devices/{serial}/screenshot` | Frame JPEG perangkat |
| `POST` | `/api/device-farm/devices/{serial}/reserve` | Reservasi perangkat |
| `DELETE` | `/api/device-farm/devices/{serial}/reserve` | Lepas reservasi |
| `GET` | `/api/farm-automation/platforms` | Platform yang didukung |
| `POST` | `/api/farm-automation/runs` | Fan-out workflow ke perangkat |
| `GET` | `/api/farm-automation/runs/{id}` | Status gabungan run |
| `POST` | `/api/farm-automation/runs/{id}/stop` | Hentikan run |
| `POST` | `/api/farm-automation/ml/preview` | Simulasi ML dan rencana akun/perangkat |
| `POST` | `/api/farm-automation/ml/feedback` | Perbarui bobot dari keputusan operator |

## Struktur penting

```text
backend/mobile_session.py       # logic aplikasi Android lintas platform
backend/farm_automation.py      # fan-out dan agregasi status farm
backend/ml_engagement.py        # model ML dry-run + account planner
backend/stf_api.py              # adapter STF + screenshot
frontend/app/device-farm/       # Control Center
scripts/start-local.ps1         # launcher lengkap
scripts/start-windows-adb-farm.ps1
docker-compose.local.yml        # wiring localhost Windows
```

Penggunaan harus mematuhi izin akun, aturan platform, dan hukum setempat.
Automation tidak dijalankan otomatis ketika stack dinyalakan.

## Lisensi

Kode integrasi mengikuti lisensi proyek ini. Komponen pihak ketiga tetap tunduk
pada lisensinya masing-masing; lihat [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
