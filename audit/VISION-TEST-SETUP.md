# AI Vision Test untuk STF

Status: terpasang dan aktif dalam mode aman `dry-run`.

## Tujuan

Panel **Vision Test** mengambil screenshot dari satu perangkat STF, meminta model vision mengusulkan objek UI yang relevan, lalu menerapkan policy lokal sebelum sebuah kandidat boleh ditampilkan sebagai `ALLOW`, `REVIEW`, atau `BLOCK`.

Respons model tidak pernah langsung menjadi perintah ADB. Policy lokal tetap menjadi otoritas akhir.

## Konfigurasi lokal

Edit file `D:\GodamSTF-ControlCenter\app\.env.localhost` dan isi sendiri nilai berikut. Jangan menaruh API key di frontend atau mengirimkannya melalui chat.

```env
OPENAI_API_KEY=isi_api_key_anda_di_mesin_ini
OPENAI_VISION_MODEL=gpt-4.1-mini
VISION_TEST_ALLOWED_PACKAGES=com.perusahaan.aplikasi.debug
VISION_TEST_EXECUTION_ENABLED=false
```

`VISION_TEST_ALLOWED_PACKAGES` menerima beberapa package yang dipisahkan koma. Gunakan hanya package aplikasi milik Anda, misalnya versi debug atau staging.

Setelah mengubah konfigurasi, muat ulang backend:

```powershell
Set-Location -LiteralPath 'D:\GodamSTF-ControlCenter\app'
& 'C:\Program Files\Docker\Docker\resources\bin\docker.exe' compose --env-file .env.localhost -f docker-compose.yml -f docker-compose.stf.yml -f docker-compose.local.yml up -d --no-deps --force-recreate backend
```

## Alur penggunaan

1. Buka `http://localhost:3000/device-farm`.
2. Pilih **Vision Test**.
3. Pilih perangkat STF yang siap.
4. Pastikan aplikasi debug/staging milik Anda sedang menjadi aplikasi aktif di perangkat.
5. Masukkan package yang sama persis dengan allowlist.
6. Tulis sasaran pengujian yang sempit, misalnya “buka halaman Profil dari layar utama”.
7. Jalankan analisis dan periksa kandidat `ALLOW`, `REVIEW`, atau `BLOCK`.

Mode default tidak menekan perangkat. Jika eksekusi benar-benar diperlukan untuk pengujian internal, ubah `VISION_TEST_EXECUTION_ENABLED=true`, restart backend, lalu operator tetap harus memilih satu kandidat `ALLOW` secara eksplisit. Kembalikan ke `false` setelah sesi pengujian.

## Guardrail yang aktif

- Package aplikasi harus sama dengan aplikasi Android yang sedang fokus.
- Package harus ada di allowlist server.
- Package media sosial, pesan, email, Settings, Play Store, dan installer diblokir.
- Login, OTP, izin, pembayaran, pembelian, penghapusan, publikasi, pesan, serta engagement sosial selalu diblokir oleh policy lokal.
- Confidence di bawah `0.75` dan input form masuk status `REVIEW`.
- Analisis klik kedaluwarsa setelah 120 detik dan package diperiksa ulang tepat sebelum klik.
- API key hanya berada di backend dan tidak muncul pada endpoint konfigurasi frontend.

## Endpoint

- `GET /api/vision-test/config`
- `POST /api/vision-test/analyze`
- `GET /api/vision-test/analyses/{analysis_id}`
- `POST /api/vision-test/analyses/{analysis_id}/click`

## Verifikasi 8 Oktober 2026

- 34 pengujian backend lulus, termasuk delapan pengujian khusus Vision Test.
- ESLint frontend lulus.
- Build produksi frontend dan backend lulus.
- Backend dan frontend sehat setelah deployment.
- QA browser menunjukkan panel Vision Test tanpa error console.
- Tidak ada screenshot yang dikirim ke OpenAI dan tidak ada perangkat yang diklik selama QA karena API key/allowlist belum diisi dan mode eksekusi tetap `false`.
