param(
    [string]$ProjectRoot = "."
)

$ErrorActionPreference = "Stop"

$tsPath = Join-Path $ProjectRoot "resources/i18n/rnmr_es.ts"
$qmPath = Join-Path $ProjectRoot "resources/i18n/rnmr_es.qm"

if (-not (Test-Path $tsPath)) {
    throw "TS file not found: $tsPath"
}

$lrelease = Get-Command pyside6-lrelease -ErrorAction SilentlyContinue
if (-not $lrelease) {
    $lrelease = Get-Command lrelease -ErrorAction SilentlyContinue
}
if (-not $lrelease) {
    Write-Host "lrelease not found in PATH."
    Write-Host "Install Qt Linguist tools and rerun:"
    Write-Host "  pyside6-lrelease resources/i18n/rnmr_es.ts -qm resources/i18n/rnmr_es.qm"
    exit 1
}

& $lrelease.Source $tsPath -qm $qmPath
Write-Host "Built $qmPath"
