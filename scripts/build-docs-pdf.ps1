param(
    [string]$PdfPath = (Join-Path (Split-Path -Parent $PSScriptRoot) "docs\StockPulse.pdf")
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = (Get-Command python -ErrorAction Stop).Source
}

& $python (Join-Path $PSScriptRoot "build-docs-pdf.py")
if ($LASTEXITCODE -ne 0) {
    throw "PDF generation failed with exit code $LASTEXITCODE"
}
if (-not (Test-Path $PdfPath)) {
    throw "Expected PDF was not written: $PdfPath"
}
Write-Host "Wrote $PdfPath ($([math]::Round((Get-Item $PdfPath).Length / 1KB, 1)) KB)"
