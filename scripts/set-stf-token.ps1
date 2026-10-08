[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateLength(8, 512)]
    [string]$Token
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$envFile = Join-Path $projectRoot ".env.localhost"

if ($Token -match "\s") {
    throw "Token STF tidak boleh mengandung spasi atau baris baru."
}
if (-not (Test-Path -LiteralPath $envFile)) {
    throw ".env.localhost belum ada. Jalankan scripts/start-local.ps1 terlebih dahulu."
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker tidak ditemukan."
}

$content = Get-Content -LiteralPath $envFile -Raw
$content = [regex]::Replace(
    $content,
    "(?m)^STF_TOKEN=.*$",
    { param($match) "STF_TOKEN=$Token" }
)
Set-Content -LiteralPath $envFile -Value $content -Encoding utf8

$composeArgs = @(
    "compose",
    "--env-file", $envFile,
    "-f", (Join-Path $projectRoot "docker-compose.yml"),
    "-f", (Join-Path $projectRoot "docker-compose.stf.yml"),
    "-f", (Join-Path $projectRoot "docker-compose.local.yml")
)
& docker @composeArgs up -d --force-recreate backend
if ($LASTEXITCODE -ne 0) {
    throw "Token tersimpan, tetapi backend gagal direstart."
}

Write-Host "Token STF tersimpan dan backend sudah direstart." -ForegroundColor Green
Write-Host "Buka dashboard: http://localhost:3000/device-farm"
