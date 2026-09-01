$ErrorActionPreference = "Stop"
$mutex = [System.Threading.Mutex]::new($false, "Global\KronosLanWatchdog")

if (-not $mutex.WaitOne(0)) {
    exit 0
}

try {
    $healthy = $false
    try {
        $site = Invoke-WebRequest "http://127.0.0.1:5173/" -UseBasicParsing -TimeoutSec 3
        $api = Invoke-WebRequest "http://127.0.0.1:5173/api/v1/health" -UseBasicParsing -TimeoutSec 3
        $backend = Invoke-WebRequest "http://127.0.0.1:8000/api/v1/health" -UseBasicParsing -TimeoutSec 3
        $healthy = $site.StatusCode -eq 200 -and $api.StatusCode -eq 200 -and $backend.StatusCode -eq 200
    } catch {
        $healthy = $false
    }

    if (-not $healthy) {
        $publisher = Join-Path $PSScriptRoot "publish-kronos-lan.ps1"
        & powershell -NoProfile -ExecutionPolicy Bypass -File $publisher -SkipChecks -SkipBuild
        exit $LASTEXITCODE
    }
} finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
