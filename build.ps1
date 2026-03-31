param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if ($Clean) {
    if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
    if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
}

$python = if (Test-Path ".venv\Scripts\python.exe") {
    ".\.venv\Scripts\python.exe"
} else {
    "python"
}

& $python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Error "Falha ao instalar dependencias (pip)."
    exit $LASTEXITCODE
}

$browserDir = Join-Path $PSScriptRoot "playwright-browsers"
New-Item -ItemType Directory -Force -Path $browserDir | Out-Null
$env:PLAYWRIGHT_BROWSERS_PATH = (Resolve-Path $browserDir).Path
Write-Host "Baixando Chromium para: $($env:PLAYWRIGHT_BROWSERS_PATH)"
& $python -m playwright install chromium
if ($LASTEXITCODE -ne 0) {
    Write-Error "Falha ao instalar Chromium do Playwright."
    exit $LASTEXITCODE
}

$hasBrowser = Get-ChildItem -Path $browserDir -ErrorAction SilentlyContinue | Where-Object { $_.Name -like "chromium-*" }
if (-not $hasBrowser) {
    Write-Error "playwright-browsers nao contem chromium-* apos playwright install."
    exit 1
}

& $python -m PyInstaller --noconfirm MyworkPontoBot.spec
if ($LASTEXITCODE -ne 0) {
    Write-Error "Falha no build do PyInstaller."
    exit $LASTEXITCODE
}
Write-Host "Build concluido: dist\MyworkPontoBot.exe"
