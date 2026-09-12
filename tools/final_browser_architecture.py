from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "windows" / "launcher.py"
APP = ROOT / "app.py"

BROWSER_MAIN = r'''def main():
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

    # Keep this EXE alive so Flask download workers continue after the browser
    # window is closed. The installer terminates this process during uninstall.
    while True:
        time.sleep(60)
'''

launcher = LAUNCHER.read_text(encoding="utf-8")
if "def launch_browser_app(" not in launcher:
    raise SystemExit("Final browser patch requires launch_browser_app().")
launcher, count = re.subn(
    r'def main\(\):[\s\S]*?\n\nif __name__ == "__main__":\n    main\(\)',
    BROWSER_MAIN + '\n\nif __name__ == "__main__":\n    main()',
    launcher,
    count=1,
)
if count != 1:
    raise SystemExit("Could not replace the generated Windows GUI main().")
LAUNCHER.write_text(launcher, encoding="utf-8")

# Add browser-native endpoints without importing tkinter on Android or server
# environments. They are only used by Windows local-browser UI controls.
app = APP.read_text(encoding="utf-8")
if "# AVD BROWSER NATIVE WINDOWS ACTIONS" not in app:
    block = r'''# AVD BROWSER NATIVE WINDOWS ACTIONS
@app.get("/api/native/browse-folder")
def native_browse_folder():
    if sys.platform != "win32":
        return jsonify({"error": "Folder browsing is only available on Windows."}), 400
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(parent=root, title="Choose Video Download Folder", initialdir=str(DOWNLOAD_DIR))
        root.destroy()
        if selected:
            DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
            globals()["DOWNLOAD_DIR"] = Path(selected).resolve()
            globals()["DOWNLOAD_DIR"].mkdir(parents=True, exist_ok=True)
        return jsonify({"path": str(DOWNLOAD_DIR)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/native/open-folder")
def native_open_folder():
    if sys.platform != "win32":
        return jsonify({"error": "Folder opening is only available on Windows."}), 400
    try:
        import os
        DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(str(DOWNLOAD_DIR))
        return jsonify({"path": str(DOWNLOAD_DIR)})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/native/open-file/<path:filename>")
def native_open_file(filename):
    if sys.platform != "win32":
        return jsonify({"error": "File opening is only available on Windows."}), 400
    try:
        import os
        target = (DOWNLOAD_DIR / Path(filename).name).resolve()
        root = DOWNLOAD_DIR.resolve()
        if target.exists() and target.parent == root:
            subprocess.Popen(["explorer", "/select," + str(target)], close_fds=True)
            return jsonify({"path": str(target)})
        return jsonify({"error": "File not found."}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


'''
    if "from flask import Flask" in app and "import sys\n" not in app.split("app = Flask", 1)[0]:
        app = app.replace("import re\n", "import re\nimport sys\n", 1)
    marker = "# =========================================================\n# HOME"
    if marker not in app:
        raise SystemExit("Home route marker not found in app.py.")
    app = app.replace(marker, block + marker, 1)
    APP.write_text(app, encoding="utf-8")

print("Final Windows architecture: Flask remains the backend; the embedded WebView2 renderer is removed from the GUI path and the installed system browser is used in app mode.")
