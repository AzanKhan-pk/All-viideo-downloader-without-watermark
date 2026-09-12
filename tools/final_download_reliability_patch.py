from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"

text = APP.read_text(encoding="utf-8")

# Required imports for persistent job state and public image downloads.
if "import os\n" not in text:
    text = text.replace("import subprocess\n", "import subprocess\nimport os\nimport json\nimport mimetypes\nimport urllib.request\n", 1)
if "from urllib.parse import urlparse, urljoin\n" not in text:
    text = text.replace("from urllib.parse import urlparse\n", "from urllib.parse import urlparse, urljoin\n", 1)

# The earlier persistence patch uses LOCALAPPDATA and therefore needs os on both
# Windows and Android. Make the state location deterministic and persistent.
if "# AVD PERSISTENCE + IMAGE GALLERY" in text:
    text = text.replace(
        'STATE_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "All Video Downloader Without Watermark"',
        'STATE_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "All Video Downloader Without Watermark"',
        1,
    )
else:
    marker = "jobs = {}\njobs_lock = threading.Lock()"
    state = '''# AVD PERSISTENCE + IMAGE GALLERY\nSTATE_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "All Video Downloader Without Watermark"\nSTATE_FILE = STATE_DIR / "jobs.json"\nSTATE_DIR.mkdir(parents=True, exist_ok=True)\n_state_lock = threading.Lock()\n_state_last_write = 0.0\n\n\ndef persist_jobs(force=False):\n    global _state_last_write\n    now = time.time()\n    if not force and now - _state_last_write < 0.5:\n        return\n    try:\n        with _state_lock:\n            with jobs_lock:\n                payload = {"version": 3, "jobs": [dict(job) for job in jobs.values()]}\n            tmp = STATE_FILE.with_suffix(".tmp")\n            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")\n            tmp.replace(STATE_FILE)\n            _state_last_write = now\n    except Exception as exc:\n        print("JOB STATE SAVE ERROR:", exc)\n\n\ndef load_persisted_jobs():\n    if not STATE_FILE.exists():\n        return\n    try:\n        payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))\n        saved = payload.get("jobs", []) if isinstance(payload, dict) else []\n        with jobs_lock:\n            for saved_job in saved:\n                if not isinstance(saved_job, dict) or not saved_job.get("id"):\n                    continue\n                job = dict(saved_job)\n                if job.get("status") in {"starting", "downloading", "processing", "converting", "queued"}:\n                    job["status"] = "queued"\n                    job["worker_running"] = False\n                    job["paused"] = False\n                    job["cancel_requested"] = False\n                jobs[job["id"]] = job\n    except Exception as exc:\n        print("JOB STATE LOAD ERROR:", exc)\n\n\ndef resume_persisted_jobs():\n    load_persisted_jobs()\n    pending = []\n    with jobs_lock:\n        for job in jobs.values():\n            if job.get("status") == "queued" and job.get("url") and job.get("mode") in {"video", "audio"}:\n                pending.append(dict(job))\n    for job in pending:\n        threading.Thread(target=download_worker, args=(job["id"], job["url"], job.get("mode", "video"), int(job.get("quality") or 720)), daemon=True).start()\n    persist_jobs(force=True)\n\n'''
    text = text.replace(marker, marker + "\n\n" + state, 1)

# Replace the extractor options with a faster, more resilient configuration.
start = text.find("def extractor_options")
end = text.find("\n\n# =========================================================\n# JOBS", start)
if start != -1 and end != -1:
    extractor = '''def extractor_options(url=None):\n    options = {\n        "quiet": True,\n        "no_warnings": True,\n        "noplaylist": True,\n        "socket_timeout": 45,\n        "retries": 10,\n        "fragment_retries": 10,\n        "file_access_retries": 8,\n        "concurrent_fragment_downloads": 4,\n        "buffersize": 1024 * 1024,\n        "continuedl": True,\n        "nopart": False,\n        "overwrites": False,\n        "restrictfilenames": False,\n        "windowsfilenames": True,\n    }\n\n    # TikTok can require browser-like TLS fingerprints. Only enable curl_cffi\n    # impersonation when that optional dependency is actually installed; Android\n    # intentionally does not install it. Forcing it on Android causes avoidable\n    # download failures.\n    domain = get_domain(url or "")\n    if domain in {"tiktok.com", "vt.tiktok.com", "vm.tiktok.com", "m.tiktok.com"}:\n        try:\n            import curl_cffi  # noqa: F401\n            options.update({\n                "impersonate": "chrome-131:windows-10",\n                "http_headers": {\n                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",\n                    "Accept-Language": "en-US,en;q=0.9",\n                    "Referer": "https://www.tiktok.com/",\n                },\n            })\n        except Exception:\n            pass\n\n    return options\n'''
    text = text[:start] + extractor + text[end:]

# Prefer yt-dlp's documented quality-filtered selectors over a single extractor-
# specific format ID. This keeps video+audio selection robust across short videos,
# TikTok and Pinterest while retaining a fallback when the requested height is absent.
old = '''            if audio_format:\n\n                # Video-only + best audio.\n                format_selector = (\n                    f"{video_format_id}+bestaudio/"\n                    f"{video_format_id}"\n                )\n\n            else:\n\n                # Try the selected format itself.\n                format_selector = (\n                    str(video_format_id)\n                )\n\n            extension = "mp4"\n'''
new = '''            # Use yt-dlp's quality filter instead of locking the job to one\n            # extractor-specific format ID. It prefers the requested height,\n            # merges audio when needed, and falls back to the best available\n            # source so short-form sites do not fail on missing format IDs.\n            format_selector = (\n                f"bestvideo*[height<={quality}]+bestaudio/"\n                f"best[height<={quality}]/bestvideo*+bestaudio/best"\n            )\n\n            extension = "mp4"\n'''
if old in text:
    text = text.replace(old, new, 1)

# Persist every job update. Do not delete the history or successful files automatically.
if "def update_job(job_id, **values):" in text and "persist_jobs(force=True)" not in text[text.find("def update_job"):text.find("def get_job")]:
    old_update = '''def update_job(job_id, **values):\n\n    with jobs_lock:\n\n        if job_id in jobs:\n            jobs[job_id].update(values)\n'''
    new_update = '''def update_job(job_id, **values):\n\n    with jobs_lock:\n        if job_id in jobs:\n            jobs[job_id].update(values)\n\n    if values.get("status") in {"completed", "error", "cancelled", "paused"}:\n        persist_jobs(force=True)\n    else:\n        persist_jobs()\n'''
    if old_update in text:
        text = text.replace(old_update, new_update, 1)

# The previous image/gallery patch has a missing urllib.parse import in its fallback.
text = text.replace("urllib.parse.urljoin(url, match)", "urljoin(url, match)")

# Keep successful history forever, and only clear the temporary working directory.
# The existing worker already removes job_dir after success; this patch never removes
# the persistent STATE_FILE or final download folder.

APP.write_text(text, encoding="utf-8")
print("Final download reliability/persistence patch applied.")
