import os
import shutil
import sys
import threading
import time
from pathlib import Path

import webview

APP_NAME = "All Video Downloader Without Watermark"
PORT = 5000


def resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def prepare_runtime() -> Path:
    root = resource_root()
    data_root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "All Video Downloader Without Watermark"
    data_root.mkdir(parents=True, exist_ok=True)

    for relative in ["app.py", "templates", "static"]:
        source = root / relative
        target = data_root / relative
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        elif source.is_file():
            shutil.copy2(source, target)

    bundled_tools = root / "tools"
    if bundled_tools.exists():
        os.environ["PATH"] = str(bundled_tools) + os.pathsep + os.environ.get("PATH", "")

    return data_root


def start_server(data_root: Path):
    sys.path.insert(0, str(data_root))
    import app as downloader_app
    downloader_app.app.run(host="127.0.0.1", port=PORT, debug=False, threaded=True, use_reloader=False)


def main():
    data_root = prepare_runtime()
    server = threading.Thread(target=start_server, args=(data_root,), daemon=True)
    server.start()

    deadline = time.time() + 30
    import urllib.request
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=1) as response:
                if response.status == 200:
                    break
        except Exception:
            time.sleep(0.25)

    webview.create_window(APP_NAME, f"http://127.0.0.1:{PORT}", width=1200, height=820, min_size=(900, 650))
    webview.start()


if __name__ == "__main__":
    main()
