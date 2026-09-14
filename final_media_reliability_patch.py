"""Final focused reliability fixes for social media media jobs.

This patch leaves the existing UI/layout and normal downloader untouched.
It only fixes: Pinterest video audio merging, broader public social-image
preview/extraction, and the focused special-download allow-list.
"""

import html
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

import media_features

try:
    from curl_cffi import requests as http_requests
except Exception:
    http_requests = None

_ORIGINAL_ALLOWED_SPECIAL = media_features._allowed_special_url
_ORIGINAL_EXTRACT_INFO = media_features._extract_info
_ORIGINAL_SPECIAL_VIDEO_WORKER = media_features._special_video_worker


def _host(url):
    try:
        return urlparse(str(url)).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def _is_social(host):
    return (
        host == "tiktok.com" or host.endswith(".tiktok.com")
        or host == "pinterest.com" or host.endswith(".pinterest.com")
        or host.endswith(".pinterest.co.uk") or host.endswith(".pinterest.de")
        or host.endswith(".pinterest.fr") or host == "pin.it"
        or host == "facebook.com" or host.endswith(".facebook.com") or host == "fb.watch"
        or host == "instagram.com" or host.endswith(".instagram.com")
        or host in {"x.com", "twitter.com"} or host.endswith(".x.com") or host.endswith(".twitter.com")
        or host == "reddit.com" or host.endswith(".reddit.com")
    )


def _allowed_special_url(url):
    return bool(_ORIGINAL_ALLOWED_SPECIAL(url) or _is_social(_host(url)))


def _fetch_html(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        if http_requests is not None:
            response = http_requests.get(url, headers=headers, impersonate="chrome", timeout=30, allow_redirects=True)
            response.raise_for_status()
            return response.text, str(response.url), headers
        import urllib.request
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", "ignore"), response.geturl(), headers
    except Exception:
        return "", url, headers


def _clean(value):
    value = html.unescape(str(value or ""))
    value = value.replace("\\/", "/").replace("\\u002F", "/").replace("\\u0026", "&")
    return value.strip()


def _meta(text, names):
    for name in names:
        patterns = [
            rf'<meta[^>]+(?:property|name)=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)',
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(name)}["\']',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                value = _clean(match.group(1))
                if value.startswith(("http://", "https://")):
                    return value
    return None


def _generic_social_images(url):
    text, final_url, headers = _fetch_html(url)
    if not text:
        return None
    urls = []
    seen = set()

    def add(value):
        value = _clean(value)
        if not value.startswith(("http://", "https://")):
            return
        parsed = urlparse(value)
        identity = (parsed.netloc.lower(), parsed.path.rstrip("/").lower())
        if identity in seen:
            return
        seen.add(identity)
        urls.append(value)

    for name in ("og:image", "og:image:url", "og:image:secure_url", "twitter:image", "twitter:image:src"):
        value = _meta(text, [name])
        if value:
            add(value)

    # JSON-LD often exposes the real image for public article/photo pages.
    for match in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', text, re.I | re.S):
        raw = html.unescape(match.group(1)).strip()
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        stack = payload if isinstance(payload, list) else [payload]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                for key in ("image", "contentUrl", "thumbnailUrl"):
                    value = node.get(key)
                    if isinstance(value, str):
                        add(value)
                    elif isinstance(value, dict):
                        add(value.get("url") or value.get("contentUrl"))
                    elif isinstance(value, list):
                        for item in value:
                            add(item if isinstance(item, str) else (item or {}).get("url"))
                for value in node.values():
                    if isinstance(value, (dict, list)):
                        stack.append(value)
            elif isinstance(node, list):
                stack.extend(node)

    if not urls:
        return None
    title_match = re.search(r'<title[^>]*>(.*?)</title>', text, re.I | re.S)
    title = _clean(re.sub(r"<[^>]+>", "", title_match.group(1))) if title_match else "Pictures"
    return {
        "type": "images",
        "title": title or "Pictures",
        "source_url": final_url,
        "headers": headers,
        "images": [{"url": value, "http_headers": headers} for value in urls[:40]],
    }


def _extract_info(url):
    info = _ORIGINAL_EXTRACT_INFO(url)
    host = _host(url)
    if isinstance(info, dict) and (info.get("images") or info.get("formats") or info.get("type") == "images"):
        return info
    if _is_social(host) and host not in {"pinterest.com", "pin.it"} and not host.endswith(".pinterest.com"):
        return _generic_social_images(url) or info
    return info


def _probe_has_audio(path):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", timeout=20,
        )
        return bool(result.stdout.strip())
    except Exception:
        return False


def _pinterest_video_with_audio(job_id, url, quality):
    if "pinterest." not in _host(url) and _host(url) not in {"pin.it"}:
        return False
    job_dir = media_features.TEMP_DIR / f"pinterest_final_{job_id}"
    job_dir.mkdir(parents=True, exist_ok=True)
    started_at = time.time()
    try:
        info = media_features._extract_info(url)
        title = (info or {}).get("title") or "Pinterest video"
        options = media_features._options(url)
        limit = int(quality or 2160)
        selector = f"bv*[height<={limit}]+ba/b[height<={limit}]/bv*+ba/b"
        options.update({
            "format": selector,
            "outtmpl": str(job_dir / "%(title)s.%(ext)s"),
            "merge_output_format": "mp4",
            "progress_hooks": [media_features.make_progress_hook(job_id)],
            "noplaylist": True,
            "retries": 10,
            "fragment_retries": 10,
            "file_access_retries": 10,
        })
        media_features.update_job(job_id, title=title, status="downloading", started_at=started_at, worker_running=True)
        with media_features.yt_dlp.YoutubeDL(options) as ydl:
            downloaded = ydl.extract_info(url, download=True)
        files = [p for p in job_dir.iterdir() if p.is_file() and not p.name.endswith((".part", ".ytdl"))]
        if not files:
            return False
        output = max(files, key=lambda p: p.stat().st_size)
        if not _probe_has_audio(output):
            return False
        final = media_features.unique_output_path(downloaded.get("title") or title, "mp4")
        shutil.move(str(output), str(final))
        media_features._finish_job(job_id, final, started_at)
        return True
    except Exception as error:
        print(f"[{job_id}] Pinterest final audio attempt: {error}")
        return False
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def _special_video_worker(job_id, url, quality):
    if _pinterest_video_with_audio(job_id, url, quality):
        return
    return _ORIGINAL_SPECIAL_VIDEO_WORKER(job_id, url, quality)


media_features._allowed_special_url = _allowed_special_url
media_features._extract_info = _extract_info
media_features._special_video_worker = _special_video_worker
