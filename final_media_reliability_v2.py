"""Final reliability patch v2.

Fixes: Pinterest video audio muxing, public social image extraction,
true final file size reporting, and completed-card folder placement.
"""
import hashlib
import html
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import core_app
import media_features

try:
    from curl_cffi import requests as http_requests
except Exception:
    http_requests = None

_ORIGINAL_EXTRACT_INFO = media_features._extract_info
_ORIGINAL_SPECIAL_VIDEO_WORKER = media_features._special_video_worker
_ORIGINAL_ALLOWED_SPECIAL = media_features._allowed_special_url


def _host(url):
    try:
        return urlparse(str(url)).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _social(host):
    return (host == "tiktok.com" or host.endswith(".tiktok.com") or
            host == "pinterest.com" or host.endswith(".pinterest.com") or host == "pin.it" or
            host == "facebook.com" or host.endswith(".facebook.com") or host == "fb.watch" or
            host == "instagram.com" or host.endswith(".instagram.com") or
            host in {"x.com", "twitter.com"} or host.endswith(".x.com") or host.endswith(".twitter.com") or
            host == "reddit.com" or host.endswith(".reddit.com"))


def _allowed(url):
    return bool(_ORIGINAL_ALLOWED_SPECIAL(url) or _social(_host(url)))


def _fetch_html(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
               "Accept-Language": "en-US,en;q=0.9", "Accept": "text/html,application/xhtml+xml,image/avif,image/webp,*/*;q=0.8"}
    try:
        if http_requests is not None:
            r = http_requests.get(url, headers=headers, impersonate="chrome", timeout=30, allow_redirects=True)
            r.raise_for_status()
            return r.text, str(r.url), headers
        import urllib.request
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "ignore"), r.geturl(), headers
    except Exception:
        return "", url, headers


def _clean(v):
    return html.unescape(str(v or "")).replace("\\/", "/").replace("\\u002F", "/").replace("\\u0026", "&").strip()


def _image_id(url):
    try:
        p = urlparse(str(url))
        return (p.netloc.lower(), p.path.rstrip("/").lower())
    except Exception:
        return str(url).lower()


def _html_images(url):
    text, final_url, headers = _fetch_html(url)
    if not text:
        return []
    out, seen = [], set()
    def add(value):
        value = _clean(value)
        if not value.startswith(("http://", "https://")):
            return
        ident = _image_id(value)
        if ident in seen:
            return
        seen.add(ident)
        out.append({"url": value, "http_headers": headers})

    # Explicit social image metadata.
    for name in ("og:image", "og:image:url", "og:image:secure_url", "twitter:image", "twitter:image:src"):
        for pattern in (rf'<meta[^>]+(?:property|name)=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)',
                        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(name)}["\']'):
            m = re.search(pattern, text, re.I)
            if m:
                add(m.group(1)); break

    # Public page JSON often contains a complete photo/slideshow URL list.
    for raw in re.findall(r'https?://[^\s"\'<>\\]+', text, re.I):
        value = _clean(raw).rstrip("\\,;)")
        low = value.lower()
        if any(x in low for x in (".jpg", ".jpeg", ".png", ".webp", ".gif", "/image", "/photo", "/picture")):
            add(value)
        if len(out) >= 40: break

    # JSON-LD image fields.
    for m in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', text, re.I | re.S):
        try: payload = json.loads(html.unescape(m.group(1)).strip())
        except Exception: continue
        stack = payload if isinstance(payload, list) else [payload]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                for key in ("image", "contentUrl", "thumbnailUrl"):
                    value = node.get(key)
                    if isinstance(value, str): add(value)
                    elif isinstance(value, dict): add(value.get("url") or value.get("contentUrl"))
                    elif isinstance(value, list):
                        for item in value: add(item if isinstance(item, str) else (item or {}).get("url"))
                for value in node.values():
                    if isinstance(value, (dict, list)): stack.append(value)
            elif isinstance(node, list): stack.extend(node)
    return out[:40]


def _extract_info(url):
    info = _ORIGINAL_EXTRACT_INFO(url)
    if not _social(_host(url)):
        return info
    extra = _html_images(url)
    if not extra:
        return info
    if not isinstance(info, dict):
        return {"type": "images", "title": "Pictures", "images": extra}
    merged = dict(info)
    images = list(info.get("images") or [])
    seen = {_image_id(x.get("url")) for x in images if isinstance(x, dict) and x.get("url")}
    for item in extra:
        if _image_id(item["url"]) not in seen:
            seen.add(_image_id(item["url"])); images.append(item)
    merged["images"] = images[:40]
    return merged


def _has_audio(path):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20)
        return bool(r.stdout.strip())
    except Exception:
        return False


def _pinterest_worker(job_id, url, quality):
    host = _host(url)
    if not ("pinterest." in host or host == "pin.it"):
        return False
    work = core_app.TEMP_DIR / f"pinterest_v2_{job_id}"
    work.mkdir(parents=True, exist_ok=True)
    started = time.time()
    try:
        info = media_features._extract_info(url) or {}
        title = info.get("title") or "Pinterest video"
        limit = int(quality or 2160)
        formats = info.get("formats") or []
        videos = [f for f in formats if isinstance(f, dict) and f.get("format_id") and f.get("vcodec") not in (None, "none")]
        audios = [f for f in formats if isinstance(f, dict) and f.get("format_id") and f.get("acodec") not in (None, "none") and f.get("vcodec") in (None, "none")]
        videos.sort(key=lambda f: (int(f.get("height") or 0), f.get("tbr") or 0), reverse=True)
        audios.sort(key=lambda f: (f.get("abr") or 0, f.get("tbr") or 0), reverse=True)
        selectors = [f"bv*[height<={limit}]+ba/b[height<={limit}]/bv*+ba/b"]
        if videos and audios:
            video = next((f for f in videos if int(f.get("height") or 0) <= limit), videos[-1])
            selectors.insert(0, f"{video['format_id']}+{audios[0]['format_id']}")
        for selector in selectors:
            try:
                options = media_features._options(url)
                options.update({"format": selector, "outtmpl": str(work / "%(title)s.%(ext)s"), "merge_output_format": "mp4", "progress_hooks": [core_app.make_progress_hook(job_id)], "noplaylist": True, "retries": 10, "fragment_retries": 10, "file_access_retries": 10})
                core_app.update_job(job_id, title=title, status="downloading", started_at=started, worker_running=True)
                with media_features.yt_dlp.YoutubeDL(options) as ydl:
                    downloaded = ydl.extract_info(url, download=True)
                files = [p for p in work.iterdir() if p.is_file() and not p.name.endswith((".part", ".ytdl"))]
                if not files: continue
                video = max(files, key=lambda p: p.stat().st_size)
                if not _has_audio(video):
                    for audio in files:
                        if audio != video and audio.suffix.lower() in (".m4a", ".aac", ".webm", ".mp3"):
                            merged = work / "merged.mp4"
                            r = subprocess.run(["ffmpeg", "-y", "-i", str(video), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart", str(merged)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
                            if r.returncode == 0 and merged.exists() and _has_audio(merged): video = merged; break
                if _has_audio(video):
                    final = core_app.unique_output_path(downloaded.get("title") or title, "mp4")
                    shutil.move(str(video), str(final)); media_features._finish_job(job_id, final, started); return True
                shutil.rmtree(work, ignore_errors=True); work.mkdir(parents=True, exist_ok=True)
            except Exception as exc:
                print(f"[{job_id}] Pinterest audio attempt failed: {exc}")
        return False
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _special_video_worker(job_id, url, quality):
    if _pinterest_worker(job_id, url, quality): return
    return _ORIGINAL_SPECIAL_VIDEO_WORKER(job_id, url, quality)


def _stable_hook(job_id):
    def hook(data):
        job = core_app.get_job(job_id)
        if not job: return
        if job.get("cancel_requested"): raise media_features.yt_dlp.utils.DownloadError("Download cancelled by user.")
        if job.get("paused"): raise core_app.PauseDownload("Download paused.")
        if data.get("status") == "downloading":
            downloaded = data.get("downloaded_bytes") or 0
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            speed = data.get("speed") or 0; eta = data.get("eta")
            percent = (downloaded / total * 100) if total else 0
            started = job.get("started_at") or time.time()
            core_app.update_job(job_id, status="downloading", downloaded_bytes=downloaded, total_bytes=total, percentage=max(0, min(99, percent)), speed=speed, eta=eta, elapsed=max(time.time()-started, .001), filesize=None)
        elif data.get("status") == "finished":
            core_app.update_job(job_id, status="processing", percentage=100, downloaded_bytes=data.get("downloaded_bytes") or data.get("total_bytes") or 0, filesize=None)
    return hook


media_features._allowed_special_url = _allowed
media_features._extract_info = _extract_info
media_features._special_video_worker = _special_video_worker
media_features.make_progress_hook = _stable_hook
core_app.make_progress_hook = _stable_hook
