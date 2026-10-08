[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
$projectRoot = Split-Path -Parent $PSScriptRoot
$statusFile = Join-Path $projectRoot "work\connect-all-android.json"
New-Item -ItemType Directory -Path (Split-Path -Parent $statusFile) -Force | Out-Null
Remove-Item -LiteralPath $statusFile -Force -ErrorAction SilentlyContinue
Set-Content -LiteralPath $statusFile -Value '{"phase":"started"}' -Encoding utf8
trap {
    Set-Content -LiteralPath $statusFile -Value (ConvertTo-Json @{ phase = "fatal"; detail = ($_ | Out-String) }) -Encoding utf8
    exit 1
}

if (-not (Get-Command usbipd -ErrorAction SilentlyContinue)) {
    throw "usbipd-win belum terpasang."
}
Set-Content -LiteralPath $statusFile -Value '{"phase":"usbipd-ready"}' -Encoding utf8

# ADB Windows menahan composite USB Samsung. Semua proses ADB dihentikan agar
# perangkat dapat dipindahkan ke WSL; ADB utama setelah ini adalah milik STF.
Get-Process -Name adb -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2
Set-Content -LiteralPath $statusFile -Value '{"phase":"windows-adb-stopped"}' -Encoding utf8

$state = (& usbipd state | ConvertFrom-Json)
$phones = @(
    $state.Devices | Where-Object {
        $_.InstanceId -like 'USB\VID_04E8&PID_6860*'
    }
)
Set-Content -LiteralPath $statusFile -Value (ConvertTo-Json @{ phase = "devices-found"; count = $phones.Count }) -Encoding utf8
if ($phones.Count -eq 0) {
    throw "Tidak ada perangkat Android Samsung yang terdeteksi."
}

$ErrorActionPreference = "Continue"
$results = foreach ($phone in $phones) {
    $busId = $phone.BusId
    $bindOutput = (& usbipd bind --busid $busId --force 2>&1 | Out-String).Trim()
    $bindExit = $LASTEXITCODE
    if ($bindExit -ne 0 -and $bindOutput -notmatch 'already shared') {
        [pscustomobject]@{ busId = $busId; description = $phone.Description; status = 'bind_error'; detail = $bindOutput }
        continue
    }
    $attachOutput = (& usbipd attach --wsl --busid $busId 2>&1 | Out-String).Trim()
    $attachExit = $LASTEXITCODE
    [pscustomobject]@{
        busId = $busId
        description = $phone.Description
        status = if ($attachExit -eq 0 -or $attachOutput -match 'already attached') { 'attached' } else { 'attach_error' }
        detail = $attachOutput
    }
}
$ErrorActionPreference = "Stop"

$results | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $statusFile -Encoding utf8
$failed = @($results | Where-Object { $_.status -ne 'attached' })
if ($failed.Count -gt 0) {
    throw "$($failed.Count) perangkat gagal diteruskan. Lihat $statusFile"
}

Write-Host "$($results.Count) perangkat Android diteruskan ke WSL/STF." -ForegroundColor Green
