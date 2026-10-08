# Progres Automasi Satu Akun (like · komen · share · repost)

> Catatan lanjutan kerja. Dibuat 2026-10-08 setelah sesi debugging panjang.
> Semua perubahan kode SUDAH TERSIMPAN di disk dan SUDAH ter-deploy ke
> kontainer Docker (`instagram-automation-backend:local` / `...frontend:local`).

## Status saat ini: BERFUNGSI untuk Instagram (like + komentar)

Run verifikasi terakhir yang sukses penuh (2 postingan, 1 perangkat
R5CT10BPZAM, target `tvrakyat.official`):

- `likes_sent: 2, comments_posted: 2, posts_processed: 2`
- Komentar terposting terlihat nyata di layar perangkat (terverifikasi visual
  via screenshot + log "tombol kirim hilang setelah ditekan").

## Cara pakai (tidak berubah)

1. Buka http://localhost:3000/device-farm → tab **Automasi 1 Akun** (★).
2. Pilih SATU perangkat online, platform, target (username tanpa @).
3. Centang aksi → Jalankan. Log perangkat + layar langsung tampil di panel.

Endpoint: `POST /api/farm-automation/single-account/runs` (wajib tepat 1 serial).

## Akar masalah yang ditemukan & sudah diperbaiki

1. **`_tap_first_post` memilih label salah** — "3,199posts" (statistik) dan
   tab "Reels" ikut cocok pola `post`/`reel`. Sekarang kandidat wajib node
   besar (>0.12 tinggi layar) dan di bawah 62% layar.
2. **Layout profil berubah saat render** (chip "Followed by" muncul belakangan)
   → koordinat dump basi. Sekarang `_open_first_post()` verifikasi setiap tap
   (`_profile_still_visible()`) dan mengulang maks 3× dengan dump segar.
3. **Deteksi "masih di profil"** memakai kehadiran tombol Like/Komentar
   (overlay postingan tetap membawa node profil di belakangnya).
4. **`uiautomator dump` basi** — file lama dihapus (`rm -f`) sebelum dump;
   dump gagal ("could not get idle state" karena video reel) tidak lagi
   terbaca sebagai layar sekarang.
5. **Mode reel (layar tak terbaca)** — koordinat terukur + verifikasi piksel:
   - Like: tap hati (0.912w, 0.169h), verifikasi kluster merah
     (`REEL_HEART_BOX`), konfirmasi dua-kali anti frame basi, cadangan
     double-tap tengah.
   - Komentar: tap pill/field (0.40w, 0.903h → 0.883h → 0.945h), fokus
     diverifikasi via `dumpsys input_method`, ketik, tombol kirim biru
     dicari dengan warna ketat (indigo 74,93,249 / biru merek, median
     kluster ≥ 800 piksel) + wajib STABIL di dua frame.
6. **Pemulihan aplikasi** — `_ensure_app_foreground()` membuka ulang IG bila
   BACK keluar ke home screen (dulu tap buta bisa membuka aplikasi lain).
7. **Laporan** — `run_reports.summarize` tidak lagi melabeli run tanpa aksi
   komentar sebagai "no_comments_recorded".

## Yang BELUM / kandidat lanjutan

- **Share di feed reel Instagram sengaja dilewati** (sheet share tak terbaca
  tanpa pohon UI; otomasi menolak menekan kontak/DM). Share berfungsi normal
  di layar yang terbaca pohon UI (foto) + platform lain (X/TikTok/Facebook).
- **Repost** baru ada di X (tombol langsung), TikTok & Facebook (via sheet).
  Baru Instagram yang divalidasi end-to-end.

## TikTok (siap diuji, menunggu internet farm pulih)

Sesi 2026-10-08 sore ditemukan:

1. **Rail video TikTok TERBACA penuh oleh pohon UI** (beda dari reel IG):
   "Like video. 415 likes", "Share video. 8 shares", dst. Automation lama
   gagal hanya karena pola `^like$` tidak cocok. PatternSpec TikTok sudah
   diperbarui (`^like video`, `share video`, submit `^post comment`).
2. **Deep link web TikTok tidak andal** — `am start tiktok.com/@user`
   berstatus ok tapi yang terbuka feed sembarang (video akun lain!). Aksi
   bisa mendarat di akun yang salah → SUDAH DIGANTI dengan navigasi
   pencarian dalam aplikasi (`_tiktok_open_profile`): buka app → ikon
   Search → ketik username → tab Users → tap baris akun → postingan pertama.
   Sudah ter-deploy, BELUM diuji lapangan.
3. **Farm kehilangan internet saat pengujian TikTok** — semua perangkat
   `ping 8.8.8.8` = unreachable, "Active default network: none". Ini
   infrastruktur (router/hotspot mati); 5 perangkat Samsung juga lepas dari
   USB. Uji TikTok (like/repost/komentar) dan X menunggu jaringan pulih.
   WiFi perangkat tidak bisa disambungkan via adb (SecurityException di
   Android 14) — harus lewat UI Setelan atau fisik.
- **Komentar kadang terposting sebagai balasan** ke komentar pertama (tap
  field bisa kena "Reply" pada layout tertentu). Kalau mau komentar berdiri
  sendiri: setelah keyboard muncul, deteksi chip "Replying to" lalu tap ✗-nya.
- Platform TikTok/X/Facebook/Threads memakai jalur pohon UI lama; feed video
  mereka kemungkinan punya masalah "idle" yang sama — perlu uji per platform.
- Koordinat reel tervalidasi di perangkat 1080x1920 (R5CT10BPZAM). Perangkat
  lain di farm (16 unit) perlu kalibrasi serupa bila layoutnya beda jauh.
- Panel "Automasi 1 Akun" di frontend sudah punya layar langsung; tombol
  per-run "Hentikan" ada di tab Runs & Log.

## Perintah berguna

```powershell
# rebuild + restart backend saja (setelah edit kode)
cd D:\GodamSTF-ControlCenter\app
docker compose -f docker-compose.yml -f docker-compose.stf.yml `
  -f docker-compose.local.yml --env-file .env.localhost build backend
docker compose -f docker-compose.yml -f docker-compose.stf.yml `
  -f docker-compose.local.yml --env-file .env.localhost up -d --wait backend

# uji cepat satu akun
curl -X POST http://localhost:8000/api/farm-automation/single-account/runs `
  -H "Content-Type: application/json" `
  -d '{"platform":"instagram","device_serial":"R5CT10BPZAM","target":"tvrakyat.official","actions":["like","comment"],"comment_count":1,"max_posts":2,"tone":"positif"}'

# pantau log run
curl http://localhost:8000/api/farm-automation/runs
```

Catatan debugging: `uiautomator dump` dari Git Bash Windows perlu
`export MSYS_NO_PATHCONV=1` (path `/sdcard/...` diubah MSYS jadi path Windows).
Jangan rekam screenshot adb tiap 2 detik selama run — bikin timeout ADB.
