from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "windows" / "launcher.py"


def main() -> None:
    """Keep the Windows launcher on the bundled Chromium architecture.

    The project no longer uses pywebview/WebView2. Older compatibility code
    could accidentally reintroduce a WebView2 import into a generated release,
    which caused a startup NameError when pywebview was not bundled. Remove
    those obsolete lines defensively before every Windows build.
    """
    text = LAUNCHER.read_text(encoding="utf-8")

    # Never allow the retired WebView2 dependency into the desktop launcher.
    lines = text.splitlines()
    cleaned = []
    skip_env_continuation = False
    for line in lines:
        stripped = line.strip()
        if stripped == "import webview":
            continue
        if "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS" in line:
            continue
        cleaned.append(line)
    text = "\n".join(cleaned) + "\n"

    # The current architecture must launch the independent Chromium shell.
    required = (
        "def start_server(",
        "def locate_bundled_browser(",
        "def launch_browser_app(",
        "def main(",
        "if __name__ == \"__main__\":",
    )
    missing = [item for item in required if item not in text]
    if missing:
        raise SystemExit("Launcher validation failed; missing: " + ", ".join(missing))

    if "import webview" in text or "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS" in text:
        raise SystemExit("Obsolete WebView2 code remains in launcher.py")

    LAUNCHER.write_text(text, encoding="utf-8")
    print("Windows runtime compatibility patch applied; WebView2 code removed.")


if __name__ == "__main__":
    main()
