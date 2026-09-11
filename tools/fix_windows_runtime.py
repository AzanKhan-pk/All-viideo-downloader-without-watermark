from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "windows" / "launcher.py"


def main() -> None:
    """Harden the existing launcher without replacing its startup logic.

    Important: newer launchers keep run_server() nested inside main(), while
    older revisions used a top-level helper. Validate the actual server entry
    point instead of requiring one particular layout.
    """
    text = LAUNCHER.read_text(encoding="utf-8")

    # Disable GPU acceleration before importing pywebview. This is only a
    # WebView2 compatibility setting and does not replace launcher logic.
    if "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS" not in text:
        marker = "import webview\n"
        if marker in text:
            text = text.replace(
                marker,
                'import os\nos.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "--disable-gpu")\n\nimport webview\n',
                1,
            )

    # Both supported launcher layouts have start_server(). A modern launcher
    # may additionally define run_server() inside main(). Do not rewrite main.
    required = ("def start_server(", "def main(", "if __name__ == \"__main__\":")
    missing = [item for item in required if item not in text]
    if missing:
        raise SystemExit("Launcher validation failed; missing: " + ", ".join(missing))

    LAUNCHER.write_text(text, encoding="utf-8")
    print("Windows runtime compatibility patch applied without replacing launcher main().")


if __name__ == "__main__":
    main()
