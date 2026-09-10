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
from tkinter import filedialog, messagebox

import webview

APP_NAME = "All Video Downloader Without Watermark"
APP_VERSION = "1.0.5"
PORT = 5000
RELEASE_API = "https://api.github.com/repos/AzanKhan-pk/All-viideo-downloader-without-watermark/releases/latest"


class WindowsBridge:
    """Native Windows controls exposed to the web app."""

    def __init__(self, data_root):
        self.data_root = Path(data_root)
        self.download_dir = self.data_root / "downloads"

    def _root(self):
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        return root

    def browse_folder(self):
        root = self._root()
        try:
            selected = filedialog.askdirectory(
                parent=root,
                title="Choose Video Download Folder",
                initialdir=str(self.download_dir if self.download_dir.exists() else Path.home()),
            )
            if selected:
                self.set_download_folder(selected)
                return str(Path(selected))
            return str(self.download_dir)
        finally:
            root.destroy()

    def set_download_folder(self, folder):
        try:
            path = Path(str(folder)).expanduser().resolve()
            path.mkdir(parents=True, exist_ok=True)
            self.download_dir = path

            # app.py uses this module global for all new downloads.
            import app as downloader_app
            downloader_app.DOWNLOAD_DIR = path
            path.mkdir(parents=True, exist_ok=True)
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
        os.startfile(str(folder))
        return str(folder)


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


def start_server(data_root: Path):
    sys.path.insert(0, str(data_root))
    import app as downloader_app

    # Windows default location: Downloads\Video downloader
    default_download_dir = Path.home() / "Downloads" / "Video downloader"
    default_download_dir.mkdir(parents=True, exist_ok=True)
    downloader_app.DOWNLOAD_DIR = default_download_dir

    downloader_app.app.run(
        host="127.0.0.1",
        port=PORT,
        debug=False,
        threaded=True,
        use_reloader=False,
    )


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


INJECTED_UI = r"""
(() => {
  const install = () => {
    if (document.getElementById('avd-native-tools')) return;

    const style = document.createElement('style');
    style.id = 'avd-native-tools-style';
    style.textContent = `
      #avd-native-tools {
        position: fixed; right: 18px; bottom: 18px; z-index: 2147483646;
        display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end;
        font-family: Inter, Arial, sans-serif;
      }
      #avd-native-tools button, #avd-context-menu button {
        border: 0; border-radius: 10px; padding: 10px 13px;
        cursor: pointer; font-weight: 700; background: #17122b; color: white;
        box-shadow: 0 5px 18px rgba(0,0,0,.22);
      }
      #avd-native-tools button:hover, #avd-context-menu button:hover { transform: translateY(-1px); }
      #avd-folder-label {
        max-width: 310px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
        padding: 10px 12px; border-radius: 10px; background: rgba(255,255,255,.94);
        color: #17122b; font-size: 12px; box-shadow: 0 5px 18px rgba(0,0,0,.16);
      }
      #avd-context-menu {
        position: fixed; z-index: 2147483647; display: none; min-width: 190px;
        padding: 7px; border-radius: 13px; background: rgba(24,18,43,.98);
        box-shadow: 0 12px 35px rgba(0,0,0,.35);
      }
      #avd-context-menu button { display:block; width:100%; text-align:left; background:transparent; box-shadow:none; }
      #avd-context-menu button:hover { background: rgba(255,255,255,.12); }
    `;
    document.head.appendChild(style);

    const tools = document.createElement('div');
    tools.id = 'avd-native-tools';
    tools.innerHTML = `
      <div id="avd-folder-label" title="Current download folder">Download folder: loading…</div>
      <button type="button" id="avd-browse">📁 Browse location</button>
      <button type="button" id="avd-open">📂 Open folder</button>
    `;
    document.body.appendChild(tools);

    const menu = document.createElement('div');
    menu.id = 'avd-context-menu';
    menu.innerHTML = `
      <button type="button" data-action="cut">✂ Cut</button>
      <button type="button" data-action="copy">📋 Copy</button>
      <button type="button" data-action="paste">📌 Paste</button>
      <button type="button" data-action="selectall">☑ Select all</button>
    `;
    document.body.appendChild(menu);

    const api = window.pywebview && window.pywebview.api;
    const label = document.getElementById('avd-folder-label');

    const refreshFolder = () => {
      if (!api || !api.get_download_folder) {
        label.textContent = 'Download folder: Downloads\\Video downloader';
        return;
      }
      api.get_download_folder().then(path => {
        label.textContent = 'Download folder: ' + path;
        label.title = path;
      }).catch(() => {});
    };

    document.getElementById('avd-browse').onclick = () => {
      if (!api || !api.browse_folder) return;
      api.browse_folder().then(path => {
        if (typeof path === 'string') {
          label.textContent = 'Download folder: ' + path;
          label.title = path;
        }
      });
    };

    document.getElementById('avd-open').onclick = () => {
      if (api && api.open_download_folder) api.open_download_folder();
    };

    let lastInput = null;
    document.addEventListener('focusin', e => {
      if (e.target && (e.target.matches('input, textarea, [contenteditable="true"]') || e.target.isContentEditable)) {
        lastInput = e.target;
      }
    }, true);

    const focusInput = () => {
      const el = lastInput || document.activeElement;
      if (!el) return null;
      if (el.matches && el.matches('input, textarea')) return el;
      if (el.isContentEditable) return el;
      return null;
    };

    const exec = action => {
      const el = focusInput();
      if (action === 'selectall') {
        if (el && el.select) el.select();
        else document.execCommand('selectAll');
      } else if (action === 'copy') {
        document.execCommand('copy');
      } else if (action === 'cut') {
        document.execCommand('cut');
      } else if (action === 'paste') {
        if (navigator.clipboard && navigator.clipboard.readText && el) {
          navigator.clipboard.readText().then(text => {
            if (el.setRangeText) {
              const start = el.selectionStart ?? el.value.length;
              const end = el.selectionEnd ?? start;
              el.setRangeText(text, start, end, 'end');
              el.dispatchEvent(new Event('input', {bubbles:true}));
            } else if (el.isContentEditable) {
              document.execCommand('insertText', false, text);
            }
          }).catch(() => document.execCommand('paste'));
        } else {
          document.execCommand('paste');
        }
      }
    };

    document.addEventListener('contextmenu', e => {
      const target = e.target;
      if (target && (target.matches('input, textarea') || target.isContentEditable || window.getSelection()?.toString())) {
        e.preventDefault();
        menu.style.left = Math.min(e.clientX, window.innerWidth - 205) + 'px';
        menu.style.top = Math.min(e.clientY, window.innerHeight - 205) + 'px';
        menu.style.display = 'block';
      }
    }, true);

    menu.addEventListener('click', e => {
      const btn = e.target.closest('button[data-action]');
      if (!btn) return;
      exec(btn.dataset.action);
      menu.style.display = 'none';
    });

    document.addEventListener('click', e => {
      if (!menu.contains(e.target)) menu.style.display = 'none';
    }, true);
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') menu.style.display = 'none';
    });

    refreshFolder();
  };

  if (window.pywebview) {
    window.addEventListener('pywebviewready', install, {once:true});
  } else {
    window.addEventListener('load', install, {once:true});
  }
})();
"""


def main():
    check_for_update()
    data_root = prepare_runtime()

    # Set the same native default immediately so Browse/Open are consistent.
    default_download_dir = Path.home() / "Downloads" / "Video downloader"
    default_download_dir.mkdir(parents=True, exist_ok=True)
    bridge = WindowsBridge(data_root)
    bridge.download_dir = default_download_dir

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

    window = webview.create_window(
        APP_NAME,
        f"http://127.0.0.1:{PORT}",
        width=1200,
        height=820,
        min_size=(900, 650),
        text_select=True,
        js_api=bridge,
    )

    def inject_native_ui():
        try:
            window.evaluate_js(INJECTED_UI)
        except Exception:
            pass

    webview.start(func=inject_native_ui)


if __name__ == "__main__":
    main()
