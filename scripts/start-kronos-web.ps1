# Starts the StockPulse website (Vite preview) and keeps it in the foreground.
# Registered as Windows Task Scheduler task "KronosWeb" (at logon).
# Independent of Cursor: open http://localhost:5173 in a normal browser.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$frontend = Join-Path $root "frontend"
$logDir = Join-Path $root "runtime-logs"
$logFile = Join-Path $logDir "web.log"
$nodeCommand = (Get-Command node.exe -ErrorAction Stop).Source
$viteEntry = Join-Path $frontend "node_modules\vite\bin\vite.js"
$distIndex = Join-Path $frontend "dist\index.html"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Test-WebListening {
    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $client.Connect("127.0.0.1", 5173)
        $client.Close()
        return $true
    } catch {
        return $false
    }
}

if (Test-WebListening) {
    Add-Content -Path $logFile -Value "$(Get-Date -Format o) already listening on port 5173"
    exit 0
}

if (-not (Test-Path $viteEntry)) {
    throw "Vite is not installed at $viteEntry"
}

if (-not (Test-Path $distIndex)) {
    $npmCommand = (Get-Command npm.cmd -ErrorAction Stop).Source
    Push-Location $frontend
    try {
        & $npmCommand run build
        if ($LASTEXITCODE -ne 0) {
            throw "Frontend build failed with exit code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
}

Set-Location $frontend
Add-Content -Path $logFile -Value "$(Get-Date -Format o) starting website on http://localhost:5173"
$ErrorActionPreference = "Continue"
& $nodeCommand $viteEntry preview --host 0.0.0.0 --port 5173 --strictPort *>> $logFile
exit $LASTEXITCODE
