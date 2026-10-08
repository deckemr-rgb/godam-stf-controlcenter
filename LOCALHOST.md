# Godam STF Control Center — localhost Windows

Stack ini memakai **DeviceFarmer STF sebagai engine perangkat** dan menanamkan
orkestrasi Godam di atasnya. Satu Control Center mengelola layar, status, pilihan
perangkat, serta automation Instagram, TikTok, X, Facebook, dan Threads.

## Lokasi dan URL

- Source dan data kerja: `D:\GodamSTF-ControlCenter`
- Control Center: `http://localhost:3000`
- Halaman langsung: `http://localhost:3000/device-farm`
- API: `http://localhost:8000/docs`
- STF engine lanjutan: `http://localhost:7100`

## Prasyarat

- Windows 10/11 dan Docker Desktop aktif.
- PowerShell 5.1 atau lebih baru.
- Android dengan Developer Options dan USB debugging aktif.
- Kabel/hub USB yang mampu membawa data dan daya secara stabil.
- Aplikasi sosial sudah terpasang serta akun sudah login pada setiap perangkat.

Launcher menggunakan ADB Windows sebagai sumber perangkat bagi provider STF.
Ini memungkinkan 16 perangkat USB dipakai bersamaan tanpa bergantung pada slot
USB/IP virtual WSL. Binary ADB GenFarmer akan dipakai dari
`%USERPROFILE%\.genfarmer\image-search\static\adb\windows\adb.exe`.

## Menjalankan

Buka PowerShell biasa:

```powershell
Set-Location D:\GodamSTF-ControlCenter\app
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\start-local.ps1
```

Launcher akan:

1. membuat secret lokal bila `.env.localhost` belum ada;
2. melepaskan perangkat yang masih ditahan USB/IP;
3. menjalankan ADB Windows pada port 5037;
4. membangun dan menyalakan seluruh service Docker;
5. menghubungkan provider STF dan backend Godam ke ADB Windows;
6. membuka Control Center.

Untuk melihat status:

```powershell
.\scripts\status-local.ps1
```

Hasil yang sehat menampilkan `ADB Windows: 16 perangkat` dan
`STF ready: 16 / 16 perangkat`.

Untuk berhenti tanpa menghapus database atau konfigurasi:

```powershell
.\scripts\stop-local.ps1
```

## Menjalankan automation farm

1. Buka `http://localhost:3000/device-farm`.
2. Pastikan kartu perangkat berstatus **Ready** dan layar tampil.
3. Pilih beberapa perangkat atau klik **Pilih semua online**.
4. Klik **Automation**.
5. Pilih platform, target, identitas akun, tone, jumlah post, dan jumlah komentar.
6. Jalankan dan pantau progres gabungan pada panel run.

Untuk menguji logika machine learning tanpa mengirim engagement, pilih seluruh
perangkat, buka **Automation**, isi konteks konten, lalu klik **Preview ML**.
Dashboard akan menampilkan confidence like/comment/share dan jumlah switch akun
yang direkomendasikan. Preview selalu menghasilkan `execute: false`.

Godam mereservasi setiap perangkat lewat STF, membuka aplikasi native, mencari
kontrol dari accessibility tree Android, lalu menjalankan like/comment sesuai
parameter. Reservasi dilepas saat pekerjaan selesai atau dihentikan.

Gunakan hanya pada akun dan target yang memang Anda kelola atau memiliki izin.
Mulai dengan jumlah kecil karena label UI dan kebijakan tiap platform dapat
berubah. Automation sengaja tidak pernah dijalankan otomatis saat instalasi.

## Aplikasi Android yang dikenali

| Platform | Package Android |
| --- | --- |
| Instagram | `com.instagram.android` |
| TikTok | `com.zhiliaoapp.musically`, `com.ss.android.ugc.trill` |
| X | `com.twitter.android` |
| Facebook | `com.facebook.katana` |
| Threads | `com.instagram.barcelona` |

Pada instalasi ini kelima aplikasi sudah terdeteksi pada seluruh 16 perangkat;
TikTok memakai package regional `com.ss.android.ugc.trill`.

## Troubleshooting

- **Perangkat unauthorized**: buka layar Android, centang *Always allow*, lalu
  setujui dialog fingerprint RSA.
- **Jumlah perangkat kurang dari 16**: jalankan
  `.\scripts\start-windows-adb-farm.ps1`, periksa hub/kabel, lalu tunggu provider
  STF menyiapkan worker.
- **Layar tidak muncul**: refresh Control Center dan pastikan endpoint screenshot
  mengembalikan JPEG dari backend.
- **Aplikasi tidak ditemukan**: pasang package platform pada perangkat tersebut
  dan login manual satu kali.
- **Selector gagal**: ubah bahasa aplikasi ke Inggris/Indonesia atau tambahkan
  pola label baru di `backend/mobile_session.py`.
- **Docker tidak dikenali**: launcher juga mencari Docker Desktop di
  `C:\Program Files\Docker\Docker\resources\bin\docker.exe`.

## Keamanan lokal

Semua port web bind ke `127.0.0.1`. Token STF berada di backend dan tidak
dikirim ke browser. Jangan membuka auth-mock STF ke internet; gunakan VPN atau
reverse proxy berautentikasi bila farm perlu diakses dari komputer lain.
