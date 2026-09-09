# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH).parent.parent
hiddenimports = collect_submodules("webview")

a = Analysis(
    [str(root / "windows" / "launcher.py")],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / "app.py"), "."),
        (str(root / "templates"), "templates"),
        (str(root / "static"), "static"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "PySide2", "PySide6", "cefpython3"],
    noarchive=False,
)

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="All-Video-Downloader",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=str(root / "windows" / "app.ico"),
)
