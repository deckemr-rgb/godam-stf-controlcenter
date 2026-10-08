[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9]+-[0-9]+$')]
    [string]$BusId
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot ".env.localhost"

if (-not (Get-Command usbipd -ErrorAction SilentlyContinue)) {
    throw "usbipd-win belum terpasang. Buka PowerShell sebagai Administrator lalu jalankan: winget install --id dorssel.usbipd-win --exact"
}
if (-not (Test-Path -LiteralPath $envFile)) {
    throw ".env.localhost belum tersedia. Jalankan scripts/start-local.ps1 terlebih dahulu."
}

Write-Host "Membagikan USB $BusId ke WSL..." -ForegroundColor Cyan
& usbipd bind --busid $BusId --force
if ($LASTEXITCODE -ne 0) {
    throw "USB gagal di-bind. Jalankan PowerShell sebagai Administrator, lalu ulangi perintah ini."
}

& usbipd attach --wsl --busid $BusId
if ($LASTEXITCODE -ne 0) {
    throw "USB gagal diteruskan ke WSL."
}

$composeArgs = @(
    "compose",
    "--env-file", $envFile,
    "-f", (Join-Path $projectRoot "docker-compose.yml"),
    "-f", (Join-Path $projectRoot "docker-compose.stf.yml"),
    "-f", (Join-Path $projectRoot "docker-compose.local.yml")
)

& docker @composeArgs restart stf-adb
if ($LASTEXITCODE -ne 0) { throw "Service ADB STF gagal direstart." }
& docker @composeArgs restart stf-provider
if ($LASTEXITCODE -ne 0) { throw "Provider STF gagal direstart." }

Write-Host ""
Write-Host "Perangkat yang terlihat oleh STF ADB:" -ForegroundColor Green
& docker @composeArgs exec -T stf-adb adb devices -l
Write-Host "Buka http://localhost:3000/device-farm untuk memilih perangkat."
