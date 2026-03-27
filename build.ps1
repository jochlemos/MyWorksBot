param(
    [switch]$Clean
)

if ($Clean) {
    if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
    if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
    if (Test-Path "MyworkPontoBot.spec") { Remove-Item -Force "MyworkPontoBot.spec" }
}

pyinstaller --noconfirm --onefile --windowed --name MyworkPontoBot main.py
Write-Host "Build concluido: dist\\MyworkPontoBot.exe"
