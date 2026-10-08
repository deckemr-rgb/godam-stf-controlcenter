[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$adb = Join-Path $env:USERPROFILE ".genfarmer\image-search\static\adb\windows\adb.exe"
if (-not (Test-Path -LiteralPath $adb)) {
    throw "ADB Windows tidak ditemukan di $adb"
}

$listeners = @(Get-NetTCPConnection -LocalPort 5037 -State Listen -ErrorAction SilentlyContinue)
if ($listeners.Count -gt 0) {
    if (-not ($listeners | Where-Object { $_.LocalAddress -in @('0.0.0.0', '::') })) {
        throw "ADB port 5037 hanya lokal. Sesi yang aktif tidak dihentikan otomatis. Setelah menutup sesi perangkat, jalankan ADB dengan -a -P 5037 agar dapat dijangkau Docker."
    }
    Write-Host "Memakai ADB yang sudah aktif; sesi perangkat dipertahankan." -ForegroundColor Cyan
} else {
    & $adb -a -P 5037 start-server | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "ADB server Windows gagal dijalankan."
    }
}

$inventory = & $adb -P 5037 devices
if ($LASTEXITCODE -ne 0) { throw "Inventaris ADB tidak dapat dibaca." }
$devices = @($inventory | Where-Object { $_ -match '\sdevice$' })
if ($devices.Count -eq 0) {
    Write-Warning "Belum ada perangkat siap. Periksa kabel, otorisasi RSA, dan USB/IP. Tidak ada perangkat USB yang dilepas otomatis."
}
Write-Host "$($devices.Count) perangkat tersedia di ADB Windows." -ForegroundColor Green
$devices
