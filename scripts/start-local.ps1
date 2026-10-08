[CmdletBinding()]
param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot ".env.localhost"
$templateFile = Join-Path $projectRoot ".env.localhost.example"

function Resolve-DockerCommand {
    $command = Get-Command docker -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }

    $desktopDocker = Join-Path $env:ProgramFiles "Docker\Docker\resources\bin\docker.exe"
    if (Test-Path -LiteralPath $desktopDocker) { return $desktopDocker }
    throw "Docker belum tersedia. Instal Docker Desktop/Engine, lalu jalankan script ini lagi."
}

function New-RandomHex([int]$byteCount) {
    $bytes = New-Object byte[] $byteCount
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
    return [BitConverter]::ToString($bytes).Replace("-", "").ToLowerInvariant()
}

function New-FernetKey {
    $bytes = New-Object byte[] 32
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
    return [Convert]::ToBase64String($bytes).Replace("+", "-").Replace("/", "_")
}

$docker = Resolve-DockerCommand
$env:Path = (Split-Path -Parent $docker) + ";" + $env:Path

& $docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker tersedia tetapi engine belum aktif. Jalankan Docker Desktop/Engine terlebih dahulu."
}

if (-not (Test-Path -LiteralPath $envFile)) {
    if (-not (Test-Path -LiteralPath $templateFile)) {
        throw "Template .env.localhost.example tidak ditemukan."
    }
    $content = Get-Content -LiteralPath $templateFile -Raw
    $content = $content.Replace("__FERNET_KEY__", (New-FernetKey))
    $content = $content.Replace("__SECRET_KEY__", (New-RandomHex 32))
    $content = $content.Replace("__POSTGRES_PASSWORD__", (New-RandomHex 24))
    $content = $content.Replace("__STF_SECRET__", (New-RandomHex 32))
    Set-Content -LiteralPath $envFile -Value $content -Encoding utf8
    Write-Host "Dibuat: .env.localhost dengan secret lokal acak." -ForegroundColor Green
}

$composeArgs = @(
    "compose",
    "--env-file", $envFile,
    "-f", (Join-Path $projectRoot "docker-compose.yml"),
    "-f", (Join-Path $projectRoot "docker-compose.stf.yml"),
    "-f", (Join-Path $projectRoot "docker-compose.local.yml")
)

& $docker @composeArgs config --quiet
if ($LASTEXITCODE -ne 0) {
    throw "Konfigurasi Docker Compose localhost tidak valid."
}

if ($env:OS -eq "Windows_NT") {
    Write-Host "Menyiapkan ADB Windows untuk device farm..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "start-windows-adb-farm.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "ADB Windows gagal disiapkan."
    }
}

& $docker @composeArgs up -d --build --wait
if ($LASTEXITCODE -ne 0) {
    throw "Sebagian service gagal dimulai. Jalankan scripts/status-local.ps1 untuk melihat status."
}

$tokenLine = Get-Content -LiteralPath $envFile | Where-Object { $_ -like "STF_TOKEN=*" } | Select-Object -First 1
$hasToken = $tokenLine -and $tokenLine.Substring("STF_TOKEN=".Length).Trim()

if (-not $hasToken) {
    Write-Host "Mengaktifkan token integrasi STF..." -ForegroundColor Cyan
    & (Join-Path $PSScriptRoot "bootstrap-stf-token.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "Stack aktif, tetapi token integrasi STF gagal dibuat."
    }
    $tokenLine = Get-Content -LiteralPath $envFile | Where-Object { $_ -like "STF_TOKEN=*" } | Select-Object -First 1
    $hasToken = $tokenLine -and $tokenLine.Substring("STF_TOKEN=".Length).Trim()
}

Write-Host ""
Write-Host "Godam localhost aktif:" -ForegroundColor Green
Write-Host "  Portal     http://localhost:3000"
Write-Host "  API docs   http://localhost:8000/docs"
Write-Host "  STF        http://localhost:7100"

if (-not $NoBrowser) {
    Start-Process "http://localhost:3000"
}
