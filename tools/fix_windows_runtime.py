from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "windows" / "launcher.py"


def main() -> None:
    text = LAUNCHER.read_text(encoding="utf-8")

    main_block = r'''def main():
    global PORT
    os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "--disable-gpu")

    data_root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AllVideoDownloader"
    data_root.mkdir(parents=True, exist_ok=True)

    PORT = find_free_port()
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    if not wait_for_server(PORT, timeout=30):
        detail = startup_error or "Local service did not become ready."
        messagebox.showerror(
            "All Video Downloader",
            "The app could not start its local service.\n\n"
            f"Details: {detail}\n\n"
            "Please restart the app. No browser page was opened.",
        )
        return

    url = f"http://127.0.0.1:{PORT}/"
    window = webview.create_window(
        "All Video Downloader Without Watermark",
        url,
        width=1200,
        height=800,
        min_size=(900, 650),
        background_color="#ffffff",
    )

    tray_icon = create_tray_icon(window)

    def on_closed():
        return

    window.events.closed += on_closed
    webview.start(storage_path=str(data_root / "webview2"), private_mode=True)

    if tray_icon is not None:
        try:
            tray_icon.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()'''

    pattern = r"def main\(\):[\s\S]*?\n\nif __name__ == \"__main__\":\n    main\(\)"
    text, count = re.subn(pattern, lambda _m: main_block, text, count=1)
    if count != 1:
        raise SystemExit("Patch target not found: launcher main block")

    LAUNCHER.write_text(text, encoding="utf-8")
    print("Windows runtime patch applied successfully.")


if __name__ == "__main__":
    main()
