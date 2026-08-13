# Starts the StockPulse FastAPI backend and keeps it in the foreground.
# Registered as Windows Task Scheduler task "KronosAPI" (at logon and startup).
# App settings live in backend/.env; process lifetime is this script + the scheduled task.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$backend = Join-Path $root "backend"
$logDir = Join-Path $backend "logs"
$logFile = Join-Path $logDir "api.log"

if (-not (Test-Path $python)) {
    throw "Python venv not found at $python"
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Test-ApiListening {
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $client.Connect("127.0.0.1", 8000)
        $client.Close()
        return $true
    } catch {
        return $false
    }
}

if (Test-ApiListening) {
    Add-Content -Path $logFile -Value "$(Get-Date -Format o) already listening on port 8000"
    exit 0
}

Set-Location $backend
$env:PYTHONUNBUFFERED = "1"
$bindHost = if ($env:KRONOS_API_HOST) { $env:KRONOS_API_HOST } else { "127.0.0.1" }
& $python -m uvicorn app.main:app --host $bindHost --port 8000 *>> $logFile
exit $LASTEXITCODE
