# -*- mode: python ; coding: utf-8 -*-
import os

# Chromium instalado em playwright-browsers/ por build.ps1 (PLAYWRIGHT_BROWSERS_PATH).
_spec_dir = os.path.dirname(os.path.abspath(SPEC))
_browser_dir = os.path.join(_spec_dir, "playwright-browsers")
if not os.path.isdir(_browser_dir) or not any(os.scandir(_browser_dir)):
    raise SystemExit(
        "Pasta playwright-browsers/ vazia ou inexistente. "
        "Execute build.ps1 (baixa o Chromium antes do PyInstaller)."
    )

datas = [(_browser_dir, "playwright-browsers")]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MyworkPontoBot",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
