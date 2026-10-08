[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$statusFile = Join-Path $projectRoot "work\usbipd-install.status"
New-Item -ItemType Directory -Path (Split-Path -Parent $statusFile) -Force | Out-Null
Remove-Item -LiteralPath $statusFile -Force -ErrorAction SilentlyContinue

try {
    Get-Process -Name winget -ErrorAction SilentlyContinue | Stop-Process -Force
    Get-Process -Name msiexec -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Seconds 2

    & winget install --id dorssel.usbipd-win --exact --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) {
        throw "winget gagal dengan exit code $LASTEXITCODE"
    }
    Set-Content -LiteralPath $statusFile -Value "SUCCESS" -Encoding ascii
} catch {
    Set-Content -LiteralPath $statusFile -Value "ERROR: $($_.Exception.Message)" -Encoding utf8
    throw
}
