# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

# SPECPATH is the directory containing this spec file (windows/).
root = Path(SPECPATH).resolve().parent.parent
hiddenimports = [m for m in collect_submodules("webview") if ".platforms.android" not in m]

a = Analysis(
    [str(root / "windows" / "launcher.py")],
    pathex=[str(root), str(root / "windows")],
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
