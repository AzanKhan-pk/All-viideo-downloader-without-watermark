import os
import shutil
import socket
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

# WebView2 can show a completely black client area on some Windows graphics
# drivers. Set this before importing pywebview so Edge/WebView2 receives it.
os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "--disable-gpu")

import webview

APP_NAME = "All Video Downloader Without Watermark"
APP_VERSION = "1.0.63"
PORT = None
RELEASE_API = "https://api.github.com/repos/AzanKhan-pk/All-viideo-downloader-without-watermark/releases/latest"


class WindowsBridge:
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
            selected = filedialog.askdirectory(
                parent=root,
                title="Choose Video Download Folder",
                initialdir=str(self.download_dir if self.download_dir.exists() else Path.home()),
            )
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
        os.startfile(str(folder))
        return str(folder)

    def read_clipboard(self):
        """Read Windows clipboard natively so Paste never needs browser clipboard permission."""
        root = self._root()
        try:
            try:
                value = root.clipboard_get()
            except tk.TclError:
                value = ""
            return str(value or "")
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
    """Pick a local TCP port so an old/stuck process cannot break startup."""
    for candidate in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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
    downloader_app.app.run(
        host="127.0.0.1",
        port=port,
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
        answer = messagebox.askyesno(
            APP_NAME,
            f"A new version ({latest}) is available.\n\nUpdate now?",
        )
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
      #avd-native-tools { position:relative; left:auto; bottom:auto; transform:none; z-index:20; width:min(920px,calc(100% - 32px)); margin:28px auto 24px; padding:10px 0; display:flex; align-items:center; gap:8px; flex-wrap:wrap; justify-content:center; font-family:Inter,Arial,sans-serif; clear:both; }
      #avd-native-tools button { border:0; border-radius:10px; padding:10px 14px; cursor:pointer; font-weight:800; background:#17122b; color:white; box-shadow:0 5px 18px rgba(0,0,0,.22); }
      #avd-folder-label { max-width:360px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; padding:10px 12px; border-radius:10px; background:rgba(255,255,255,.96); color:#17122b; font-size:12px; box-shadow:0 5px 18px rgba(0,0,0,.16); }
      #avd-context-menu { position:fixed; z-index:2147483647; display:none; min-width:190px; padding:7px; border-radius:13px; background:rgba(24,18,43,.99); box-shadow:0 12px 35px rgba(0,0,0,.35); }
      #avd-context-menu button { display:block; width:100%; text-align:left; border:0; border-radius:9px; padding:10px 12px; cursor:pointer; background:transparent; color:white; font:700 13px Inter,Arial,sans-serif; }
      #avd-context-menu button:hover { background:rgba(255,255,255,.12); }
      @media(max-width:700px){#avd-native-tools{width:calc(100% - 20px);margin:22px auto 18px}.avd-folder-label{max-width:55vw}}
    `;
    document.head.appendChild(style);
    const tools = document.createElement('div');
    tools.id = 'avd-native-tools';
    tools.innerHTML = `
      <div id="avd-folder-label" title="Current download folder">📥 Download folder: loading…</div>
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
      if (!api || !api.get_download_folder) { label.textContent='📥 Download folder: Downloads\\Video downloader'; return; }
      api.get_download_folder().then(path => { if(typeof path==='string'){label.textContent='📥 Download folder: '+path;label.title=path;} }).catch(()=>{});
    };
    document.getElementById('avd-browse').onclick = () => {
      if (api && api.browse_folder) api.browse_folder().then(path => { if(typeof path==='string'){label.textContent='📥 Download folder: '+path;label.title=path;} });
    };
    document.getElementById('avd-open').onclick = () => { if(api && api.open_download_folder) api.open_download_folder(); };

    let lastInput=null;
    document.addEventListener('focusin',e=>{if(e.target && (e.target.matches?.('input, textarea') || e.target.isContentEditable)) lastInput=e.target;},true);
    const focusInput=()=>{const el=lastInput||document.activeElement;if(!el)return null;if(el.matches?.('input, textarea')||el.isContentEditable)return el;return null;};
    const insertText=(el,text)=>{
      if(!el || !text) return;
      if(el.setRangeText){
        const s=el.selectionStart??el.value.length;
        const e=el.selectionEnd??s;
        el.setRangeText(text,s,e,'end');
        el.dispatchEvent(new Event('input',{bubbles:true}));
        el.dispatchEvent(new Event('change',{bubbles:true}));
      } else if(el.isContentEditable){
        el.focus();
        document.execCommand('insertText',false,text);
        el.dispatchEvent(new Event('input',{bubbles:true}));
      }
    };
    const nativePaste=()=>{
      const el=focusInput();
      if(!el || !api || !api.read_clipboard) return;
      api.read_clipboard().then(text=>insertText(el,String(text||''))).catch(()=>{});
    };
    const exec=action=>{
      const el=focusInput();
      if(action==='selectall'){if(el?.select)el.select();else document.execCommand('selectAll');}
      else if(action==='copy')document.execCommand('copy');
      else if(action==='cut')document.execCommand('cut');
      else if(action==='paste')nativePaste();
    };

    document.querySelectorAll('.paste-btn, [data-action="paste"], [data-paste], [data-clipboard="paste"]').forEach(btn=>{
      btn.addEventListener('click',e=>{e.preventDefault();e.stopImmediatePropagation();nativePaste();},true);
    });

    document.addEventListener('contextmenu',e=>{
      const t=e.target, selected=window.getSelection()?.toString();
      if(t?.matches?.('input, textarea')||t?.isContentEditable||selected){
        e.preventDefault();
        menu.style.left=Math.min(e.clientX,window.innerWidth-205)+'px';
        menu.style.top=Math.min(e.clientY,window.innerHeight-205)+'px';
        menu.style.display='block';
      }
    },true);
    menu.addEventListener('click',e=>{const b=e.target.closest('button[data-action]');if(!b)return;exec(b.dataset.action);menu.style.display='none';});
    document.addEventListener('click',e=>{if(!menu.contains(e.target))menu.style.display='none';},true);
    document.addEventListener('keydown',e=>{if(e.key==='Escape')menu.style.display='none';});
    refreshFolder();
  };
  const start = () => { setTimeout(install, 250); };
  if (document.readyState === 'loading') window.addEventListener('DOMContentLoaded', start, {once:true}); else start();
})();
"""


def main():
    global PORT
    check_for_update()
    data_root = prepare_runtime()
    bridge = WindowsBridge(data_root)
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
        messagebox.showerror(
            APP_NAME,
            "The app could not start its local service.\n\n"
            f"Details: {detail}\n\n"
            "Please restart the app. No browser page was opened.",
        )
        return

    window = webview.create_window(
        APP_NAME,
        f"http://127.0.0.1:{PORT}",
        width=1200,
        height=820,
        min_size=(900, 650),
        text_select=True,
        js_api=bridge,
        background_color="#ffffff",
    )

    def inject_native_ui():
        try:
            window.evaluate_js(INJECTED_UI)
        except Exception:
            pass

    window.events.loaded += inject_native_ui
    webview.start(gui="edgechromium", debug=False)


if __name__ == "__main__":
    main()
