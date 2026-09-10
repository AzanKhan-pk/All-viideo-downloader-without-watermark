import os
import shutil
import sys
import threading
import time
from pathlib import Path
import json
import subprocess
import urllib.request
import tempfile
import tkinter as tk
from tkinter import messagebox

import webview

APP_NAME = "All Video Downloader Without Watermark"
APP_VERSION = "1.0.4"
PORT = 5000
RELEASE_API = "https://api.github.com/repos/AzanKhan-pk/All-viideo-downloader-without-watermark/releases/latest"


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


def version_tuple(value):
    try:
        return tuple(int(x) for x in value.lstrip("v").split(".")[:3])
    except Exception:
        return (0, 0, 0)


def check_for_update():
    try:
        req = urllib.request.Request(RELEASE_API, headers={"User-Agent": APP_NAME})
        with urllib.request.urlopen(req, timeout=5) as response:
            release = json.load(response)
        latest = str(release.get("tag_name", ""))
        if version_tuple(latest) <= version_tuple(APP_VERSION):
            return
        assets = release.get("assets", [])
        asset = next((a for a in assets if a.get("name", "").lower().endswith("setup.exe")), None)
        if not asset:
            return
        answer = messagebox.askyesno(APP_NAME, f"A new version ({latest}) is available.\n\nUpdate now?")
        if not answer:
            return
        target = Path(tempfile.gettempdir()) / "All-Video-Downloader-Update.exe"
        urllib.request.urlretrieve(asset["browser_download_url"], target)
        subprocess.Popen([str(target)], close_fds=True)
        raise SystemExit(0)
    except SystemExit:
        raise
    except Exception:
        pass


def main():
    check_for_update()
    data_root = prepare_runtime()
    server = threading.Thread(target=start_server, args=(data_root,), daemon=True)
    server.start()
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=1) as response:
                if response.status == 200:
                    break
        except Exception:
            time.sleep(0.25)
    webview.create_window(APP_NAME, f"http://127.0.0.1:{PORT}", width=1200, height=820, min_size=(900, 650), text_select=True)
    webview.start()


if __name__ == "__main__":
    main()
