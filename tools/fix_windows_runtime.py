from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "windows" / "launcher.py"

text = LAUNCHER.read_text(encoding="utf-8")

# The persistence/gallery build patch adds tray/background behavior. Keep that
# behavior, but restore the hardened startup sequence so the server is actually
# started on a free port and the WebView never opens a dead/blank localhost page.
main_block = r'''def main():
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
            "Please restart the app. No browser page was opened."
        )
        return

    window = webview.create_window(
        APP_NAME,
        f"http://127.0.0.1:{PORT}/",
        width=1200,
        height=820,
        min_size=(900, 650),
        text_select=True,
        js_api=bridge,
        background_color="#ffffff",
    )

    state = {"allow_exit": False}
    tray_icon = None

    def on_closing():
        # Normal close keeps downloads alive in the tray/background.
        if state["allow_exit"]:
            return True
        try:
            window.hide()
            if tray_icon is not None:
                tray_icon.title = "All Video Downloader — downloading in background"
        except Exception:
            pass
        return False

    def show_window(icon=None, item=None):
        try:
            window.show()
            window.restore()
        except Exception:
            pass

    def exit_app(icon=None, item=None):
        state["allow_exit"] = True
        try:
            if icon is not None:
                icon.stop()
        except Exception:
            pass
        try:
            window.destroy()
        except Exception:
            pass

    def start_tray():
        nonlocal tray_icon
        if pystray is None or Image is None:
            return
        try:
            tray_icon = pystray.Icon(
                "All Video Downloader",
                _make_tray_image(),
                "All Video Downloader",
                menu=pystray.Menu(
                    pystray.MenuItem("Open Downloader", show_window, default=True),
                    pystray.MenuItem("Exit", exit_app),
                ),
            )
            tray_icon.run()
        except Exception as exc:
            print("TRAY ERROR:", exc)

    def inject_native_ui(window_obj):
        try:
            window_obj.evaluate_js(INJECTED_UI)
        except Exception:
            pass

    window.events.closing += on_closing
    window.events.loaded += inject_native_ui
    threading.Thread(target=start_tray, daemon=True).start()

    # A writable per-user WebView2 profile avoids stale/corrupt browser data in
    # the Program Files installation directory. Software GPU rendering avoids
    # the Windows WebView2 black-surface issue on affected graphics drivers.
    webview.start(
        storage_path=str(data_root / "webview2"),
        private_mode=True,
    )
'''

text, count = re.subn(
    r"def main\(\):[\s\S]*?\n\nif __name__ == \"__main__\":\n    main\(\)",
    main_block + '\n\nif __name__ == "__main__":\n    main()',
    text,
    count=1,
)
if count != 1:
    raise SystemExit("Patch target not found: launcher main runtime block")

# WebView2 GPU workaround must be set before importing pywebview.
marker = "import webview\n"
insert = 'os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "--disable-gpu")\n\n'
if insert.strip() not in text:
    if marker not in text:
        raise SystemExit("Patch target not found: pywebview import")
    text = text.replace(marker, insert + marker, 1)

LAUNCHER.write_text(text, encoding="utf-8")
print("Windows runtime startup, WebView2 black-screen protection, and tray shutdown behavior fixed.")
