$ErrorActionPreference = "Continue"
$ensure = Join-Path $PSScriptRoot "ensure-kronos-lan.ps1"
$root = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $root "runtime-logs"
$logFile = Join-Path $logDir "watchdog.log"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

while ($true) {
    try {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $ensure
        if ($LASTEXITCODE -ne 0) {
            Add-Content -Path $logFile -Value "$(Get-Date -Format o) health recovery exited $LASTEXITCODE"
        }
    } catch {
        Add-Content -Path $logFile -Value "$(Get-Date -Format o) watchdog error: $($_.Exception.Message)"
    }
    Start-Sleep -Seconds 30
}
