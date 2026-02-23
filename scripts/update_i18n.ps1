param(
    [string]$ProjectRoot = ".",
    [switch]$UseQtExtractor
)

$ErrorActionPreference = "Stop"

$sources = @(
    "gui/main_window.py",
    "gui/settings_dialog.py",
    "gui/setup_wizard.py",
    "gui/support_dialog.py",
    "gui/failed_lookup_dialog.py",
    "gui/media_type_dialog.py",
    "gui/tmdb_select_dialog.py",
    "gui/id_dialog.py",
    "gui/search_dialog.py"
)

$tsPath = Join-Path $ProjectRoot "resources/i18n/rnmr_es.ts"
$lupdate = Get-Command pyside6-lupdate -ErrorAction SilentlyContinue
if (-not $lupdate) {
    $lupdate = Get-Command lupdate -ErrorAction SilentlyContinue
}

if (-not $lupdate) {
    throw "lupdate not found in PATH. Install PySide6 tools (pyside6-lupdate)."
}

if (-not $UseQtExtractor) {
    Write-Host "This project currently uses gui/i18n.py fallback keys (t(...))."
    Write-Host "Qt lupdate cannot extract those keys automatically."
    Write-Host "Use -UseQtExtractor only if you migrate strings to self.tr()/QCoreApplication.translate."
    exit 0
}

$sourcePaths = $sources | ForEach-Object { Join-Path $ProjectRoot $_ }
& $lupdate.Source @sourcePaths -ts $tsPath
Write-Host "Updated $tsPath"
