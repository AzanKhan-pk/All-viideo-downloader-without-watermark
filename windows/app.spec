# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

# Resolve the repository root from this spec file without relying on runtime paths.
root = Path.cwd().resolve()
if (root / "windows" / "launcher.py").exists():
    pass
elif (root.parent / "windows" / "launcher.py").exists():
    root = root.parent
else:
    raise SystemExit(f"Repository root not found. cwd={root}")

launcher = root / "windows" / "launcher.py"

# Windows no longer embeds WebView2. The Flask UI is rendered by the installed
# system browser in app mode, so no WebView2 hidden imports or runtime hook are
# needed in the executable.
a = Analysis(
    [str(launcher)],
    pathex=[str(root), str(root / "windows")],
    binaries=[],
    datas=[
        (str(root / "app.py"), "."),
        (str(root / "templates"), "templates"),
        (str(root / "static"), "static"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["android", "PyQt5", "PyQt6", "PySide2", "PySide6", "cefpython3", "webview"],
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
