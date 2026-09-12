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
        messagebox.showerror(APP_NAME, "The app could not start its local service.\n\nDetails: " + detail)
        return

    url = f"http://127.0.0.1:{PORT}"
    if not launch_browser_app(url, data_root):
        messagebox.showerror(APP_NAME, "No web browser could be opened for the app.")
        return

    while True:
        time.sleep(60)
'''

launcher = LAUNCHER.read_text(encoding="utf-8")
if "def launch_browser_app(" not in launcher:
    raise SystemExit("Final browser patch requires launch_browser_app().")
if not re.search(r"^import os\s*$", launcher, re.M):
    launcher = "import os\n" + launcher
launcher, count = re.subn(
    r'def main\(\):[\s\S]*?\n\nif __name__ == "__main__":\n    main\(\)',
    lambda _match: BROWSER_MAIN + '\n\nif __name__ == "__main__":\n    main()',
    launcher,
    count=1,
)
if count != 1:
    raise SystemExit("Could not replace the generated Windows GUI main().")
LAUNCHER.write_text(launcher, encoding="utf-8")

# Add browser-native Windows endpoints when the app has a recognizable home-route marker.
# If the marker is absent because the current app layout has moved, do not fail the build:
# the browser architecture does not depend on these optional endpoints.
app = APP.read_text(encoding="utf-8")
if "# AVD BROWSER NATIVE WINDOWS ACTIONS" not in app:
    block = r'''# AVD BROWSER NATIVE WINDOWS ACTIONS
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
        target = (DOWNLOAD_DIR / Path(filename).name).resolve()
        root = DOWNLOAD_DIR.resolve()
        if target.exists() and target.parent == root:
            subprocess.Popen(["explorer", "/select," + str(target)], close_fds=True)
            return jsonify({"path": str(target)})
        return jsonify({"error": "File not found."}), 404
    except Exception as exc:
        return jsonify({"error": str(exc)}), 404

'''
    if "import sys\n" not in app.split("app = Flask", 1)[0]:
        app = app.replace("import re\n", "import re\nimport sys\n", 1)
    marker = "# =========================================================\n# HOME"
    if marker in app:
        app = app.replace(marker, block + marker, 1)
        APP.write_text(app, encoding="utf-8")
    else:
        print("Optional native endpoint marker not present; skipping endpoint insertion.")

print("Final Windows architecture patch completed: installed system browser app mode is used instead of embedded WebView2.")
