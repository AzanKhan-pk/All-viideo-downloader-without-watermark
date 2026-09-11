from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"

text = APP.read_text(encoding="utf-8")

old = '''def extractor_options():
    return {
        "quiet": True,
        "no_warnings": True,

        # Don't download playlists accidentally.
        "noplaylist": True,

        "socket_timeout": 30,

        "retries": 5,
        "fragment_retries": 5,
        "file_access_retries": 5,

        # Allows interrupted downloads to continue.
        "continuedl": True,

        "nopart": False,

        "overwrites": False,

        "restrictfilenames": False,
        "windowsfilenames": True,
    }
'''

new = '''def extractor_options(url=None):
    options = {
        "quiet": True,
        "no_warnings": True,

        # Don't download playlists accidentally.
        "noplaylist": True,

        "socket_timeout": 30,

        "retries": 8,
        "fragment_retries": 8,
        "file_access_retries": 8,

        # Allows interrupted downloads to continue.
        "continuedl": True,

        "nopart": False,

        "overwrites": False,

        "restrictfilenames": False,
        "windowsfilenames": True,
    }

    # TikTok has recently been sensitive to HTTP/TLS fingerprints. yt-dlp
    # officially supports browser impersonation through curl_cffi for sites
    # that use this kind of fingerprinting. Keep it TikTok-specific so other
    # extractors are not slowed down or affected.
    if url and get_domain(url) in {
        "tiktok.com",
        "vt.tiktok.com",
        "vm.tiktok.com",
        "m.tiktok.com",
    }:
        options.update({
            "impersonate": "chrome",
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/140.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.tiktok.com/",
            },
        })

    return options
'''

if old not in text:
    raise SystemExit("Patch target not found: extractor_options")
text = text.replace(old, new, 1)

# Make every extraction/download/info request use the URL-aware options.
text = text.replace("extractor_options()", "extractor_options(url)")

APP.write_text(text, encoding="utf-8")
print("TikTok-focused yt-dlp extraction patch applied.")
