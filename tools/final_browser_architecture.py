from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "windows" / "launcher.py"

# Compatibility shim: the Windows launcher now owns the renderer architecture.
# Never rewrite it during CI, because doing so would reintroduce external-browser
# launching and undo the native WebView2 window.
text = LAUNCHER.read_text(encoding="utf-8")
required = ("import webview", "def launch_native_window(", 'webview.start(gui="edgechromium"')
missing = [item for item in required if item not in text]
if missing:
    raise SystemExit("Native Windows renderer validation failed; missing: " + ", ".join(missing))
print("Native Windows renderer already configured; no launcher rewrite performed.")
