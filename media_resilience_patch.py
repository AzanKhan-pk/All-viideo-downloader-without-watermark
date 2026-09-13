"""Focused resilience layer for public TikTok/Pinterest media.

It deliberately sits on top of the stable downloader instead of replacing it.
It rejects HTML error pages masquerading as media, supports Pinterest HLS
playlists through FFmpeg, and broadens public-page media URL discovery.
"""

import re
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse
import urllib.request

import core_app
import media_features
import site_fallbacks
from flask import jsonify, request


_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36"
)


def _headers(source_url, extra=None):
    result = {"User-Agent": _UA, "Referer": source_url}
    for key, value in (extra or {}).items():
        if key and value:
            result[str(key)] = str(value)
    return result


def _is_hls(url):
    return bool(re.search(r"\.m3u8(?:$|[?#])", str(url or ""), re.I))


def _header_arg(headers):
    return "".join(f"{k}: {v}\r\n" for k, v in headers.items())


def _download_hls(url, destination, source_url, extra_headers=None):
    if not core_app.ffmpeg_available():
        raise RuntimeError("FFmpeg is required for this streaming video.")
    headers = _headers(source_url, extra_headers)
    destination = Path(destination)
    command = [
        "ffmpeg", "-y", "-headers", _header_arg(headers),
        "-i", str(url), "-map", "0:v:0?", "-map", "0:a:0?",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart", str(destination),
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0 or not destination.exists() or destination.stat().st_size <= 0:
        raise RuntimeError("The streaming media could not be read. " + result.stderr[-900:])


_ORIGINAL_DIRECT = media_features._download_direct


def _safe_download_direct(url, destination, source_url, extra_headers=None):
    url = str(url or "").strip()
    if _is_hls(url):
        return _download_hls(url, destination, source_url, extra_headers)

    headers = _headers(source_url, extra_headers)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=90) as response:
        content_type = str(response.headers.get("Content-Type") or "").lower()
        first = response.read(1024)
        sample = first.lstrip().lower()
        if "text/html" in content_type or sample.startswith(b"<!doctype html") or sample.startswith(b"<html"):
            raise RuntimeError("The media server returned a webpage instead of the media file.")
        with open(destination, "wb") as output:
            output.write(first)
            shutil.copyfileobj(response, output)
    if not Path(destination).exists() or Path(destination).stat().st_size <= 0:
        raise RuntimeError("The media server returned an empty file.")


media_features._download_direct = _safe_download_direct


# Pinterest often exposes a valid video as HLS and also exposes progressive MP4
# candidates elsewhere in the page. Add those candidates without changing the
# existing fallback parser.
_ORIGINAL_PINTEREST = site_fallbacks.pinterest


def _extra_urls_from_html(html):
    text = str(html or "").replace("\\/", "/").replace("\\u002F", "/")
    urls = []
    seen = set()
    for match in re.findall(r"https?://[^\"'<>\\\s]+", text, re.I):
        value = match.rstrip("\\,;)")
        if value in seen:
            continue
        seen.add(value)
        if any(host in value.lower() for host in ("pinimg.com", "pinterest.com", "pinterestcdn.com")):
            urls.append(value)
    return urls


def _enhanced_pinterest(url):
    result = _ORIGINAL_PINTEREST(url)
    try:
        html, final_url, headers = site_fallbacks._get(url, "https://www.pinterest.com/")
        urls = _extra_urls_from_html(html)
        videos = []
        images = []
        for value in urls:
            low = value.lower()
            if ".mp4" in low or ".m3u8" in low or "/videos/" in low:
                videos.append({"url": value, "height": 0, "http_headers": headers})
            elif ".jpg" in low or ".jpeg" in low or ".png" in low or ".webp" in low or "i.pinimg.com" in low:
                images.append({"url": value, "width": None, "height": None, "http_headers": headers})

        if result is None:
            result = {"title": "Pinterest media", "source_url": final_url, "headers": headers, "_fallback_direct": True}
        result.setdefault("headers", headers)
        result.setdefault("source_url", final_url)
        result["_fallback_direct"] = True

        existing_video = result.get("formats") or []
        existing_urls = {str(x.get("url")) for x in existing_video if isinstance(x, dict)}
        for video in videos:
            if video["url"] not in existing_urls:
                existing_video.append({
                    "format_id": f"pin-html-{len(existing_video)}",
                    "url": video["url"], "height": video.get("height") or 0,
                    "ext": "mp4" if ".m3u8" not in video["url"].lower() else "mp4",
                    "vcodec": "h264", "acodec": "aac", "http_headers": headers,
                    "protocol": "m3u8_native" if ".m3u8" in video["url"].lower() else "https",
                })
        if existing_video:
            result["type"] = "video"
            result["formats"] = existing_video

        existing_images = result.get("images") or []
        existing_image_urls = {str(x.get("url")) for x in existing_images if isinstance(x, dict)}
        for image in images:
            if image["url"] not in existing_image_urls:
                existing_images.append(image)
        if existing_images:
            result["images"] = existing_images[:40]

        return result if (result.get("formats") or result.get("images")) else None
    except Exception:
        return result


site_fallbacks.pinterest = _enhanced_pinterest


# Safe quality conversion: never upscale a smaller source.
_ORIGINAL_RESIZE = core_app.resize_video


def _safe_resize(input_file, output_file, target_height, job_id):
    if not core_app.ffmpeg_available():
        raise RuntimeError("FFmpeg is required for quality conversion.")
    core_app.update_job(job_id, status="converting", conversion=True, percentage=0)
    scale = f"scale=-2:min({int(target_height)},ih)"
    command = ["ffmpeg", "-y", "-i", str(input_file), "-vf", scale,
               "-c:v", "libx264", "-crf", "28", "-preset", "medium",
               "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(output_file)]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0 or not Path(output_file).exists() or Path(output_file).stat().st_size <= 0:
        raise RuntimeError("FFmpeg quality conversion failed. " + result.stderr[-1000:])


core_app.resize_video = _safe_resize


# Replace the preview endpoint with a JSON-safe version. In particular, a Pinterest
# fallback with images attached to a video must remain a video, not be misclassified
# as a photo gallery.
def _preview_json():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url or not media_features._allowed_special_url(url):
        return jsonify({"error": "Please use a public TikTok or Pinterest URL."}), 400
    try:
        info = media_features._extract_info(url)
        fallback = media_features._fallback_info(url)
        if not info and not fallback:
            return jsonify({"error": "The site did not return usable public media data."}), 502
        if fallback and (not info or fallback.get("type") in ("images", "video")):
            if fallback.get("type") == "video" and (not info or not info.get("formats")):
                info = fallback
            elif fallback.get("type") == "images" and not info:
                info = fallback
        info = info or fallback or {}
        images = media_features._image_candidates(info)
        if fallback:
            images = images or (fallback.get("images") or [])
        formats = info.get("formats") or []
        is_video = info.get("type") == "video" or bool(formats) or bool(info.get("url"))
        is_photo = info.get("type") == "images" or (bool(images) and not is_video)
        thumbnail = info.get("thumbnail") or info.get("thumbnail_url")
        if not thumbnail and fallback:
            thumbs = fallback.get("images") or []
            if thumbs and isinstance(thumbs[0], dict):
                thumbnail = thumbs[0].get("url")
        return jsonify({
            "success": True,
            "title": (fallback or {}).get("title") or info.get("title") or "Public media",
            "extractor": info.get("extractor_key") or info.get("extractor"),
            "is_photo": bool(is_photo),
            "thumbnail": thumbnail,
            "images": images[:40],
        })
    except Exception as error:
        return jsonify({"error": f"Media preview failed: {error}"}), 502


core_app.app.view_functions["media_preview"] = _preview_json
