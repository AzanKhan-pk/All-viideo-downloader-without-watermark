# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path.cwd().resolve()
if (root / "windows" / "launcher.py").exists():
    pass
elif (root.parent / "windows" / "launcher.py").exists():
    root = root.parent
else:
    raise SystemExit(f"Repository root not found. cwd={root}")

launcher = root / "windows" / "launcher.py"

a = Analysis(
    [str(launcher)],
    pathex=[str(root), str(root / "windows")],
    binaries=[],
    datas=[
        (str(root / "app.py"), "."),
        (str(root / "templates"), "templates"),
        (str(root / "static"), "static"),
    ],
    hiddenimports=[
        "webview",
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
        "clr",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["android", "PyQt5", "PyQt6", "PySide2", "PySide6", "cefpython3"],
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
