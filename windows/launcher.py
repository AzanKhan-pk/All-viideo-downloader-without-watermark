import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

APP_NAME = "All Video Downloader Without Watermark"
APP_VERSION = "1.0.63"
PORT = None
RELEASE_API = "https://api.github.com/repos/AzanKhan-pk/All-viideo-downloader-without-watermark/releases/latest"


class WindowsBridge:
    """Windows-only helpers retained for the existing browser UI integration."""
    def __init__(self, data_root):
        self.data_root = Path(data_root)
        self.download_dir = Path.home() / "Downloads" / "Video downloader"
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def _root(self):
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        return root

    def browse_folder(self):
        root = self._root()
        try:
            selected = filedialog.askdirectory(parent=root, title="Choose Video Download Folder", initialdir=str(self.download_dir if self.download_dir.exists() else Path.home()))
            if selected:
                return self.set_download_folder(selected)
            return str(self.download_dir)
        finally:
            root.destroy()

    def set_download_folder(self, folder):
        try:
            path = Path(str(folder)).expanduser().resolve()
            path.mkdir(parents=True, exist_ok=True)
            self.download_dir = path
            import app as downloader_app
            downloader_app.DOWNLOAD_DIR = path
            return str(path)
        except Exception as exc:
            return {"error": str(exc)}

    def get_download_folder(self):
        try:
            import app as downloader_app
            return str(downloader_app.DOWNLOAD_DIR)
        except Exception:
            return str(self.download_dir)

    def open_download_folder(self):
        folder = Path(self.get_download_folder())
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(folder))
        return str(folder)

    def open_download_file(self, filename):
        try:
            name = Path(str(filename or "")).name
            folder = Path(self.get_download_folder()).resolve()
            target = (folder / name).resolve()
            if target.exists() and target.parent == folder:
                if sys.platform == "win32":
                    subprocess.Popen(["explorer", "/select," + str(target)], close_fds=True)
                return str(target)
            self.open_download_folder()
            return str(folder)
        except Exception as exc:
            return {"error": str(exc)}

    def read_clipboard(self):
        root = self._root()
        try:
            try:
                return str(root.clipboard_get() or "")
            except tk.TclError:
                return ""
        finally:
            root.destroy()


def resource_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def prepare_runtime() -> Path:
    root = resource_root()
    data_root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME
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


def find_free_port(start=5000, attempts=100):
    for candidate in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", candidate))
                return candidate
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_server(data_root: Path, port: int):
    sys.path.insert(0, str(data_root))
    import app as downloader_app
    default_download_dir = Path.home() / "Downloads" / "Video downloader"
    default_download_dir.mkdir(parents=True, exist_ok=True)
    downloader_app.DOWNLOAD_DIR = default_download_dir
    if hasattr(downloader_app, "resume_persisted_jobs"):
        downloader_app.resume_persisted_jobs()
    downloader_app.app.run(host="127.0.0.1", port=port, debug=False, threaded=True, use_reloader=False)


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
        asset = next((a for a in release.get("assets", []) if a.get("name", "").lower().endswith("setup.exe")), None)
        if not asset or not messagebox.askyesno(APP_NAME, f"A new version ({latest}) is available.\n\nUpdate now?"):
            return
        target = Path(tempfile.gettempdir()) / "All-Video-Downloader-Update.exe"
        urllib.request.urlretrieve(asset["browser_download_url"], target)
        subprocess.Popen([str(target)], close_fds=True)
        raise SystemExit(0)
    except SystemExit:
        raise
    except Exception:
        pass


def locate_browser():
    candidates = [
        os.environ.get("PROGRAMFILES", r"C:\Program Files") + r"\Google\Chrome\Application\chrome.exe",
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)") + r"\Google\Chrome\Application\chrome.exe",
        os.environ.get("LOCALAPPDATA", "") + r"\Google\Chrome\Application\chrome.exe",
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)") + r"\Microsoft\Edge\Application\msedge.exe",
        os.environ.get("PROGRAMFILES", r"C:\Program Files") + r"\Microsoft\Edge\Application\msedge.exe",
        os.environ.get("LOCALAPPDATA", "") + r"\Microsoft\Edge\Application\msedge.exe",
        os.environ.get("LOCALAPPDATA", "") + r"\BraveSoftware\Brave-Browser\Application\brave.exe",
    ]
    for raw in candidates:
        if raw and Path(raw).is_file():
            return raw
    return None


def launch_browser_app(url, data_root):
    browser = locate_browser()
    if browser:
        profile = data_root / "BrowserProfile"
        profile.mkdir(parents=True, exist_ok=True)
        subprocess.Popen([
            browser,
            f"--app={url}",
            "--new-window",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
        ], close_fds=True)
        return True
    return bool(webbrowser.open_new(url))


def main():
    global PORT
    check_for_update()
    data_root = prepare_runtime()
    PORT = find_free_port()
    server_error = []

    def run_server():
        try:
            start_server(data_root, PORT)
        except Exception as exc:
            server_error.append(exc)

    server = threading.Thread(target=run_server, daemon=True)
    server.start()

    ready = False
    deadline = time.time() + 30
    while time.time() < deadline:
        if server_error:
            break
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=1) as response:
                if 200 <= response.status < 500:
                    ready = True
                    break
        except Exception:
            time.sleep(0.25)

    if not ready:
        detail = str(server_error[0]) if server_error else "The local app server did not start."
        messagebox.showerror(APP_NAME, "The app could not start its local service.\n\n" f"Details: {detail}")
        return

    url = f"http://127.0.0.1:{PORT}"
    if not launch_browser_app(url, data_root):
        messagebox.showerror(APP_NAME, "No web browser could be opened for the app.")
        return

    # Keep the local Flask process alive so downloads continue even when the
    # browser window is closed. Inno Setup terminates this EXE during uninstall.
    while True:
        time.sleep(60)


if __name__ == "__main__":
    main()
