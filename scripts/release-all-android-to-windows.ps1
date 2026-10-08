[CmdletBinding()]
param()

$ErrorActionPreference = "Continue"
$env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
$state = (& usbipd state | ConvertFrom-Json)
$phones = @($state.Devices | Where-Object { $_.InstanceId -like 'USB\VID_04E8&PID_6860*' })
foreach ($phone in $phones) {
    & usbipd detach --busid $phone.BusId 2>$null | Out-Null
    & usbipd unbind --busid $phone.BusId 2>$null | Out-Null
}
Write-Host "$($phones.Count) perangkat dikembalikan ke ADB Windows." -ForegroundColor Green
