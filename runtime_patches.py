import os
from pathlib import Path

import core_app


_original_extractor_options = core_app.extractor_options


def extractor_options(url=None):
    try:
        options = dict(_original_extractor_options())
    except TypeError:
        options = dict(_original_extractor_options)

    host = ""
    try:
        from urllib.parse import urlparse
        host = urlparse(url or "").netloc.lower().removeprefix("www.")
    except Exception:
        pass

    if host == "tiktok.com" or host.endswith(".tiktok.com"):
        options.setdefault("http_headers", {})
        options["http_headers"].update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.tiktok.com/",
        })

    return options


core_app.extractor_options = extractor_options

# On Windows the normal first-run location is the user's C: Downloads folder.
# Keep Android/Linux on the existing app-local directory.
if os.name == "nt":
    default_download_dir = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Downloads" / "Video downloader"
    default_download_dir.mkdir(parents=True, exist_ok=True)
    core_app.DOWNLOAD_DIR = default_download_dir
