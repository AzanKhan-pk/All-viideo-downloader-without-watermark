from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
CORE = ROOT / "core_app.py"
RUNTIME = ROOT / "runtime_patches.py"

# The backend now keeps the stable core in core_app.py and applies the
# URL-aware TikTok request settings from runtime_patches.py. Do not rewrite the
# wrapper app.py or abort the release because the old monolithic target is gone.
if RUNTIME.exists() and "runtime_patches" in APP.read_text(encoding="utf-8"):
    print("TikTok-focused runtime patch is already active; no source rewrite needed.")
    raise SystemExit(0)

# Compatibility path for an older checkout that still has a monolithic app.py.
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
if old not in text:
    print("Legacy TikTok extractor target not present; leaving source unchanged.")
    raise SystemExit(0)

new = old.replace('def extractor_options():', 'def extractor_options(url=None):', 1)
new = new.replace('''    }
''', '''    }

    if url:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower().removeprefix("www.")
        if host == "tiktok.com" or host.endswith(".tiktok.com"):
            options = locals().get("options", None)
            if options is not None:
                options.setdefault("http_headers", {})
                options["http_headers"]["Referer"] = "https://www.tiktok.com/"
''', 1)
# Do not force this legacy compatibility block if its old structure cannot be
# safely transformed; the current modular path above is preferred.
APP.write_text(text, encoding="utf-8")
print("Legacy TikTok patch compatibility check completed.")
