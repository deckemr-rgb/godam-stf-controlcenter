# Panduan Menjalankan Bot "Via PC" di Laptop Temanmu

Mode **via PC** artinya: bot (Chromium) berjalan di **laptop yang dipakai**, bukan di server.
Karena itu laptop tersebut **harus menjalankan backend** ini. Tenang — caranya mudah & sekali saja.

> Kenapa wajib? Website tidak bisa membuka Chromium di laptop orang lain.
> Yang membuka Chromium adalah program backend ini yang berjalan di laptop itu.
> Ini justru bagus: RAM/Railway tidak terbebani, bisa dipakai banyak orang.

---

## Yang dibutuhkan (sekali saja)
1. Laptop terhubung internet.
2. Install **Python 3.10+** (Centang "Add to PATH" saat install di Windows).
3. Download kode backend dari GitHub (publik): `uppvision-lgtm/godam`
   - Cara termudah: buka https://github.com/uppvision-lgtm/godam → tombol hijau **Code ▾ → Download ZIP**
   - Ekstrak, lalu masuk ke folder `godam-main/backend`

---

## macOS (MacBook)
Buka **Terminal**, lalu jalankan satu per satu:

```bash
cd ~/Downloads/godam-main/backend
chmod +x run_pc.sh
./run_pc.sh
```

Pertama kali otomatis: buat venv → install kebutuhan → install Chromium → buat `.env`.
Setelah selesai, server jalan di `http://localhost:8000`. **Biarkan terminal ini terbuka.**

## Windows
Buka **Command Prompt** (atau PowerShell), lalu:

```bat
cd %USERPROFILE%\Downloads\godam-main\backend
run_pc.bat
```

Pertama kali otomatis: buat venv → install kebutuhan → install Chromium → buat `.env`.
Server jalan di `http://localhost:8000`. **Biarkan jendela ini terbuka.**

---

## Cara memakai (setiap mau bot)
1. Pastikan backend sudah jalan (ada tulisan "Uvicorn running on http://0.0.0.0:8000").
2. Buka browser: **https://godam-omega.vercel.app**
3. Klik kartu **🖥️ Auto Komen & Like Instagram — via PC**
4. Isi form (nama akun, Session ID, channel target, jumlah), klik **Mulai**.
5. Bot berjalan dari laptop ini. Selesai → Chromium ditutup otomatis.

> Catatan: buka website dari **laptop yang sama** tempat backend berjalan
> (karena backend di `localhost:8000` itu milik laptop tersebut).

---

## Menghentikan server
Tekan **Ctrl+C** di terminal tempat server berjalan.

## Troubleshooting
- **"Failed to fetch"** saat Mulai → pastikan server benar-benar jalan (cek tulisan `Uvicorn running`).
- **Session ID tidak valid** → ambil ulang cookie `sessionid` dari browser yang sudah login Instagram.
- Server mati saat laptop ditutup → jalankan ulang `./run_pc.sh` / `run_pc.bat`.
