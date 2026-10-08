[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot ".env.localhost"
$docker = (Get-Command docker -ErrorAction SilentlyContinue).Source
if (-not $docker) {
    $docker = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
}
if (-not (Test-Path -LiteralPath $docker)) {
    throw "Docker CLI tidak ditemukan. Jalankan Docker Desktop terlebih dahulu."
}

& $docker compose `
    --env-file $envFile `
    -f (Join-Path $projectRoot "docker-compose.yml") `
    -f (Join-Path $projectRoot "docker-compose.stf.yml") `
    -f (Join-Path $projectRoot "docker-compose.local.yml") `
    ps

if ($env:OS -eq "Windows_NT") {
    $adb = Join-Path $env:USERPROFILE ".genfarmer\image-search\static\adb\windows\adb.exe"
    if (Test-Path -LiteralPath $adb) {
        $adbDevices = @(& $adb devices | Where-Object { $_ -match '\sdevice$' })
        Write-Host ""
        Write-Host "ADB Windows: $($adbDevices.Count) perangkat" -ForegroundColor Cyan
    }
    try {
        $farm = Invoke-RestMethod -Uri "http://localhost:8000/api/device-farm/devices" -TimeoutSec 10
        $ready = @($farm.devices | Where-Object { $_.present -and $_.ready }).Count
        Write-Host "STF ready: $ready / $(@($farm.devices).Count) perangkat" -ForegroundColor Green
    } catch {
        Write-Warning "Status API STF belum tersedia."
    }
}
