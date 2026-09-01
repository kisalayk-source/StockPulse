param(
    [switch]$SkipChecks,
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"
$runtimeDir = Join-Path $root "runtime-logs"
$pidFile = Join-Path $runtimeDir "lan-publish-pids.json"
$watchdogPidFile = Join-Path $runtimeDir "lan-watchdog.pid"
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    $pythonCommand = Get-Command python -ErrorAction Stop
    $python = (& $pythonCommand.Source -c "import sys; print(sys.executable)").Trim()
}

$npmCommand = (Get-Command npm.cmd -ErrorAction Stop).Source
$nodeCommand = (Get-Command node.exe -ErrorAction Stop).Source
$viteEntry = Join-Path $frontend "node_modules\vite\bin\vite.js"
New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory
    )
    Push-Location $WorkingDirectory
    try {
        & $FilePath @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "$FilePath $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
        }
    } finally {
        Pop-Location
    }
}

if (-not $SkipChecks) {
    Invoke-Checked $python @("-m", "pytest", "-q") $backend
    Invoke-Checked $npmCommand @("run", "lint") $frontend
    Invoke-Checked $npmCommand @("run", "typecheck") $frontend
    Invoke-Checked $npmCommand @("test") $frontend
}
if (-not $SkipBuild) {
    Invoke-Checked $npmCommand @("run", "build") $frontend
}

if (Test-Path $pidFile) {
    $published = Get-Content $pidFile -Raw | ConvertFrom-Json
    foreach ($processId in @($published.backend, $published.frontend)) {
        if (-not $processId) { continue }
        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($process) {
            Stop-Process -Id $processId -Force
            Wait-Process -Id $processId -ErrorAction SilentlyContinue
        }
    }
    Remove-Item $pidFile -Force
}

foreach ($port in @(8000, 5173)) {
    $listener = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
    if ($listener) {
        $owner = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener[0].OwningProcess)" -ErrorAction SilentlyContinue
        if ($owner.CommandLine -match "app\.main:app|Kronos.*vite\.js") {
            Stop-Process -Id $listener[0].OwningProcess -Force
            Wait-Process -Id $listener[0].OwningProcess -ErrorAction SilentlyContinue
        } else {
            throw "Port $port is already in use by process $($listener[0].OwningProcess). Stop it before publishing."
        }
    }
}

$backendProcess = Start-Process `
    -FilePath $python `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") `
    -WorkingDirectory $backend `
    -RedirectStandardOutput (Join-Path $runtimeDir "backend.stdout.log") `
    -RedirectStandardError (Join-Path $runtimeDir "backend.stderr.log") `
    -WindowStyle Hidden `
    -PassThru

$backendReady = $false
$backendDeadline = (Get-Date).AddSeconds(30)
do {
    Start-Sleep -Milliseconds 500
    try {
        $directBackendHealth = Invoke-WebRequest "http://127.0.0.1:8000/api/v1/health" -UseBasicParsing -TimeoutSec 2
        if ($directBackendHealth.StatusCode -eq 200) {
            $backendReady = $true
            break
        }
    } catch {
        if ((Get-Date) -ge $backendDeadline) {
            Stop-Process -Id $backendProcess.Id -Force -ErrorAction SilentlyContinue
            throw "Backend did not become healthy on port 8000 before the timeout."
        }
    }
} while ((Get-Date) -lt $backendDeadline)

$frontendProcess = Start-Process `
    -FilePath $nodeCommand `
    -ArgumentList @($viteEntry, "preview", "--host", "0.0.0.0", "--port", "5173") `
    -WorkingDirectory $frontend `
    -RedirectStandardOutput (Join-Path $runtimeDir "frontend.stdout.log") `
    -RedirectStandardError (Join-Path $runtimeDir "frontend.stderr.log") `
    -WindowStyle Hidden `
    -PassThru

@{
    backend = $backendProcess.Id
    frontend = $frontendProcess.Id
    published_at = (Get-Date -Format o)
} | ConvertTo-Json | Set-Content -Path $pidFile -Encoding UTF8

try {
    $deadline = (Get-Date).AddSeconds(30)
    do {
        Start-Sleep -Milliseconds 500
        try {
            $frontendHealth = Invoke-WebRequest "http://127.0.0.1:5173/" -UseBasicParsing -TimeoutSec 2
            $apiHealth = Invoke-WebRequest "http://127.0.0.1:5173/api/v1/health" -UseBasicParsing -TimeoutSec 2
            if ($frontendHealth.StatusCode -eq 200 -and $apiHealth.StatusCode -eq 200) {
                break
            }
        } catch {
            if ((Get-Date) -ge $deadline) { throw }
        }
    } while ((Get-Date) -lt $deadline)

    if (-not $frontendHealth -or -not $apiHealth) {
        throw "Published services did not become healthy before the timeout."
    }
} catch {
    Stop-Process -Id $backendProcess.Id, $frontendProcess.Id -Force -ErrorAction SilentlyContinue
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    throw "Local network publish failed: $($_.Exception.Message)"
}

$watchdogProcess = $null
if (Test-Path $watchdogPidFile) {
    $watchdogPid = Get-Content $watchdogPidFile -ErrorAction SilentlyContinue
    if ($watchdogPid) {
        $watchdogProcess = Get-Process -Id $watchdogPid -ErrorAction SilentlyContinue
    }
}
if (-not $watchdogProcess) {
    $watchdogScript = Join-Path $PSScriptRoot "watch-kronos-lan.ps1"
    $watchdogProcess = Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList @("-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-File", $watchdogScript) `
        -WindowStyle Hidden `
        -PassThru
    Set-Content -Path $watchdogPidFile -Value $watchdogProcess.Id -Encoding ASCII
}

$addresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
        $_.IPAddress -notlike "127.*" -and
        $_.IPAddress -notlike "169.254.*" -and
        $_.InterfaceAlias -notmatch "Loopback|vEthernet|WSL|Docker"
    } |
    Select-Object -ExpandProperty IPAddress -Unique

Write-Host "StockPulse published successfully."
Write-Host "Local: http://localhost:5173"
foreach ($address in $addresses) {
    Write-Host "LAN:   http://${address}:5173"
}
