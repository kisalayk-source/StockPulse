param(
    [string]$ArchitecturePdf = (Join-Path (Split-Path -Parent $PSScriptRoot) "docs\StockPulse-Architecture.pdf"),
    [string]$GlossaryPdf = (Join-Path (Split-Path -Parent $PSScriptRoot) "docs\StockPulse-Finance-Glossary.pdf")
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}

& $python (Join-Path $PSScriptRoot "build-guide-pdfs.py")
if ($LASTEXITCODE -ne 0) {
    throw "Guide PDF generation failed with exit code $LASTEXITCODE"
}
foreach ($path in @($ArchitecturePdf, $GlossaryPdf)) {
    if (-not (Test-Path $path)) {
        throw "Expected PDF was not written: $path"
    }
    Write-Host "Wrote $path ($([math]::Round((Get-Item $path).Length / 1KB, 1)) KB)"
}
