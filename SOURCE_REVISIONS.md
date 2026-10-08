# Source revisions

Integrasi ini dibuat pada 8 Oktober 2026 dari:

- Godam: `uppvision-lgtm/godam` commit
  `6c7780d4aad15a9de85c13e7888ce6b1e2cf2b86`.
- DeviceFarmer STF: `DeviceFarmer/stf` commit
  `be79c0c9546ceb2da761c9ff2ada29d68c1f5f23`.

URL awal `uppvision-lgtm/godamtesting` tidak tersedia (404). Akun tersebut
hanya menampilkan repository publik `godam`, sehingga repository itulah yang
digunakan sebagai aplikasi utama sesuai klarifikasi bahwa file Godam harus
menerima fitur farm.

STF tidak disalin ke monorepo. Ia dijalankan dari image resminya sebagai
sekumpulan service terisolasi melalui `docker-compose.stf.yml`, sementara
Godam mengakses REST API STF lewat adapter `backend/stf_api.py`.
