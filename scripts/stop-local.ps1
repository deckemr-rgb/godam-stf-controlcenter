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
    throw "Docker CLI tidak ditemukan."
}

if (-not (Test-Path -LiteralPath $envFile)) {
    throw ".env.localhost tidak ditemukan."
}

& $docker compose `
    --env-file $envFile `
    -f (Join-Path $projectRoot "docker-compose.yml") `
    -f (Join-Path $projectRoot "docker-compose.stf.yml") `
    -f (Join-Path $projectRoot "docker-compose.local.yml") `
    down

if ($LASTEXITCODE -ne 0) {
    throw "Gagal menghentikan stack localhost."
}
Write-Host "Stack localhost dihentikan. Volume database dan media tetap tersimpan." -ForegroundColor Green
