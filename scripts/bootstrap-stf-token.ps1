[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot ".env.localhost"
$composeArgs = @(
    "compose",
    "--env-file", $envFile,
    "-f", (Join-Path $projectRoot "docker-compose.yml"),
    "-f", (Join-Path $projectRoot "docker-compose.stf.yml"),
    "-f", (Join-Path $projectRoot "docker-compose.local.yml")
)

if (-not (Test-Path -LiteralPath $envFile)) {
    throw ".env.localhost belum tersedia."
}

& docker @composeArgs cp (Join-Path $PSScriptRoot "bootstrap-stf-token.js") "stf-api:/tmp/bootstrap-stf-token.js"
if ($LASTEXITCODE -ne 0) {
    throw "Gagal menyalin bootstrap token ke container STF."
}

$token = (& docker @composeArgs exec -T stf-api node /tmp/bootstrap-stf-token.js).Trim()
if ($LASTEXITCODE -ne 0 -or $token.Length -lt 32) {
    throw "Gagal membuat token integrasi STF."
}

& (Join-Path $PSScriptRoot "set-stf-token.ps1") -Token $token
if ($LASTEXITCODE -ne 0) {
    throw "Token dibuat tetapi gagal dipasang ke backend Godam."
}

Write-Host "Integrasi STF server-to-server aktif." -ForegroundColor Green
