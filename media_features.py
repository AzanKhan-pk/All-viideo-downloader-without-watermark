import mimetypes
import shutil
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from flask import jsonify, request, send_file

from core_app import (
    app,
    TEMP_DIR,
    DOWNLOAD_DIR,
    extractor_options,
    jobs,
    jobs_lock,
    make_progress_hook,
    unique_output_path,
    update_job,
    ffmpeg_available,
)


def _options(url=None):
    try:
        return extractor_options(url)
    except TypeError:
        return extractor_options()


def _new_job(url, kind, quality=2160):
    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {
            "id": job_id, "url": url, "domain": urlparse(url).netloc.lower(),
            "mode": kind, "quality": quality, "status": "queued",
            "title": "Preparing download...", "filename": None, "download_url": None,
            "percentage": 0, "downloaded_bytes": 0, "total_bytes": 0,
            "filesize": None, "speed": 0, "eta": None, "elapsed": 0,
            "error": None, "paused": False, "cancel_requested": False,
            "started_at": None, "finished_at": None, "worker_running": False,
            "source_height": None, "target_height": quality, "conversion": False,
        }
    return job_id


def _finish_job(job_id, final_path, started_at):
    if not final_path.exists() or final_path.stat().st_size <= 0:
        raise RuntimeError("The final media file was not created correctly.")
    size = final_path.stat().st_size
    elapsed = max(time.time() - (started_at or time.time()), 0.001)
    update_job(job_id, status="completed", percentage=100, downloaded_bytes=size,
               total_bytes=size, filesize=size, filename=final_path.name,
               download_url=f"/api/file/{final_path.name}", elapsed=elapsed,
               speed=size / elapsed, eta=0, finished_at=time.time(),
               worker_running=False, conversion=False)


def _choose_video_format(info, quality):
    limit = int(quality)
    formats = info.get("formats") or []
    combined = [f for f in formats
                if f.get("vcodec") not in (None, "none")
                and f.get("acodec") not in (None, "none")
                and f.get("height") and int(f.get("height") or 0) <= limit
                and f.get("ext") == "mp4"]
    combined.sort(key=lambda f: (int(f.get("height") or 0), f.get("tbr") or 0), reverse=True)
    if combined:
        return str(combined[0].get("format_id")), False
    if not ffmpeg_available():
        raise RuntimeError("This video needs FFmpeg to merge video and audio, but FFmpeg is not available.")
    return f"bv*[height<={limit}]+ba/b[height<={limit}]", True


def _special_video_worker(job_id, url, quality):
    job_dir = TEMP_DIR / f"special_{job_id}"
    job_dir.mkdir(parents=True, exist_ok=True)
    started_at = time.time()
    update_job(job_id, status="starting", started_at=started_at, worker_running=True)
    try:
        with yt_dlp.YoutubeDL(_options(url)) as ydl:
            info = ydl.extract_info(url, download=False)
        title = info.get("title") or "video"
        update_job(job_id, title=title, source_height=info.get("height"))
        selector, needs_merge = _choose_video_format(info, quality)
        options = _options(url)
        options.update({
            "format": selector,
            "outtmpl": str(job_dir / "%(title)s.%(ext)s"),
            "merge_output_format": "mp4",
            "progress_hooks": [make_progress_hook(job_id)],
            "noplaylist": True,
            "retries": 10,
            "fragment_retries": 10,
            "file_access_retries": 10,
        })
        if not needs_merge:
            options.pop("merge_output_format", None)
        update_job(job_id, status="downloading")
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
        update_job(job_id, title=info.get("title") or title)
        files = [p for p in job_dir.iterdir() if p.is_file() and not p.name.endswith((".part", ".ytdl"))]
        if not files:
            raise RuntimeError("Download completed, but no final video file was produced.")
        mp4s = [p for p in files if p.suffix.lower() == ".mp4"]
        output = max(mp4s or files, key=lambda p: p.stat().st_size)
        if output.stat().st_size <= 0:
            raise RuntimeError("The downloaded video file is empty.")
        final_path = unique_output_path(title, "mp4")
        shutil.move(str(output), str(final_path))
        _finish_job(job_id, final_path, started_at)
    except Exception as error:
        update_job(job_id, status="error", error=str(error), worker_running=False, finished_at=time.time(), conversion=False)
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def _walk_infos(info):
    if not isinstance(info, dict):
        return
    yield info
    for entry in info.get("entries") or []:
        if isinstance(entry, dict):
            yield from _walk_infos(entry)


def _image_candidates(info):
    candidates = []
    seen = set()
    for item in _walk_infos(info):
        raw = []
        if item.get("thumbnail"):
            raw.append({"url": item["thumbnail"], "width": None, "height": None})
        raw.extend(item.get("thumbnails") or [])
        raw.extend(item.get("images") or [])
        for thumb in raw:
            if isinstance(thumb, str):
                thumb = {"url": thumb}
            if not isinstance(thumb, dict) or not thumb.get("url"):
                continue
            image_url = thumb["url"]
            if image_url in seen:
                continue
            seen.add(image_url)
            candidates.append({
                "url": image_url,
                "width": thumb.get("width") or thumb.get("w"),
                "height": thumb.get("height") or thumb.get("h"),
                "ext": thumb.get("ext"),
                "http_headers": thumb.get("http_headers") or {},
            })
    candidates.sort(key=lambda x: ((x.get("width") or 0) * (x.get("height") or 0), x.get("width") or 0), reverse=True)
    return candidates[:40]


def _download_image(url, source_url, destination, extra_headers=None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Referer": source_url,
    }
    for key, value in (extra_headers or {}).items():
        if key and value:
            headers[str(key)] = str(value)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=45) as response, open(destination, "wb") as output:
        shutil.copyfileobj(response, output)


def _download_image_list(job_id, source_url, image_list):
    job_dir = TEMP_DIR / f"images_{job_id}"
    job_dir.mkdir(parents=True, exist_ok=True)
    started_at = time.time()
    update_job(job_id, status="starting", started_at=started_at, worker_running=True)
    saved = []
    try:
        total = len(image_list)
        for index, item in enumerate(image_list, 1):
            if not isinstance(item, dict):
                continue
            image_url = str(item.get("url") or "").strip()
            if not image_url.startswith(("http://", "https://")):
                continue
            try:
                suffix = Path(urlparse(image_url).path).suffix.lower()
                if suffix not in (".jpg", ".jpeg", ".png", ".webp"):
                    suffix = ".jpg"
                temp = job_dir / f"image_{index:03d}{suffix}"
                _download_image(image_url, source_url, temp, item.get("http_headers"))
                if temp.exists() and temp.stat().st_size > 0:
                    saved.append(temp)
            except Exception:
                continue
            update_job(job_id, status="downloading", percentage=(index / max(total, 1)) * 100,
                       downloaded_bytes=sum(p.stat().st_size for p in saved), total_bytes=0)
        if not saved:
            raise RuntimeError("No selected picture could be downloaded from this post.")
        title = "TikTok Pinterest Pictures"
        with jobs_lock:
            title = jobs.get(job_id, {}).get("title") or title
        folder = unique_output_path(title, "jpg").with_suffix("")
        folder.mkdir(parents=True, exist_ok=True)
        final_paths = []
        for index, temp in enumerate(saved, 1):
            ext = temp.suffix or ".jpg"
            target = folder / f"{index:03d}{ext}"
            shutil.move(str(temp), str(target))
            final_paths.append(target)
        size = sum(p.stat().st_size for p in final_paths)
        first_relative = f"{folder.name}/{final_paths[0].name}"
        update_job(job_id, status="completed", percentage=100, downloaded_bytes=size,
                   total_bytes=size, filesize=size, filename=folder.name,
                   download_url=f"/api/special-file/{first_relative}",
                   elapsed=max(time.time() - started_at, 0.001), eta=0,
                   finished_at=time.time(), worker_running=False)
    except Exception as error:
        update_job(job_id, status="error", error=str(error), worker_running=False, finished_at=time.time())
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def _image_worker(job_id, url):
    try:
        with yt_dlp.YoutubeDL(_options(url)) as ydl:
            info = ydl.extract_info(url, download=False)
        title = info.get("title") or "image"
        update_job(job_id, title=title)
        candidates = _image_candidates(info)
        if not candidates:
            raise RuntimeError("No downloadable pictures were found for this post.")
        _download_image_list(job_id, url, candidates[:1])
    except Exception as error:
        update_job(job_id, status="error", error=str(error), worker_running=False, finished_at=time.time())


def _allowed_special_url(url):
    domain = urlparse(url).netloc.lower().removeprefix("www.")
    return (domain == "tiktok.com" or domain.endswith(".tiktok.com")
            or domain == "pinterest.com" or domain.endswith(".pinterest.com")
            or domain.endswith(".pinterest.co.uk") or domain.endswith(".pinterest.de")
            or domain.endswith(".pinterest.fr"))


@app.post("/api/special-file/<path:relative>")
def _special_file_post(relative):
    return _special_file(relative)


@app.get("/api/special-file/<path:relative>")
def _special_file(relative):
    base = Path(DOWNLOAD_DIR).resolve()
    target = (base / relative).resolve()
    if target != base and base not in target.parents:
        return jsonify({"error": "Invalid file path."}), 400
    if not target.is_file():
        return jsonify({"error": "File was not found."}), 404
    return send_file(target, as_attachment=True, download_name=target.name)


@app.post("/api/media-preview")
def media_preview():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url or not _allowed_special_url(url):
        return jsonify({"error": "Please use a public TikTok or Pinterest URL."}), 400
    try:
        with yt_dlp.YoutubeDL(_options(url)) as ydl:
            info = ydl.extract_info(url, download=False)
        images = _image_candidates(info)
        return jsonify({
            "success": True,
            "title": info.get("title") or "Public media",
            "extractor": info.get("extractor_key") or info.get("extractor"),
            "is_photo": not bool(info.get("formats")) and bool(images),
            "images": images,
        })
    except Exception as error:
        return jsonify({"error": str(error)}), 500


@app.post("/api/special-download")
def special_download():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    kind = (data.get("kind") or "video").lower()
    if not url:
        return jsonify({"error": "URL is required."}), 400
    if not _allowed_special_url(url):
        return jsonify({"error": "This focused tool supports public TikTok and Pinterest URLs."}), 400
    try:
        quality = max(144, min(2160, int(data.get("quality", 2160))))
    except Exception:
        quality = 2160
    job_id = _new_job(url, kind, quality)
    if kind == "images":
        items = data.get("images") or []
        if not isinstance(items, list) or not items:
            return jsonify({"error": "Select at least one picture first."}), 400
        safe_items = [x for x in items if isinstance(x, dict) and str(x.get("url") or "").startswith(("http://", "https://"))][:40]
        if not safe_items:
            return jsonify({"error": "No valid selected pictures were received."}), 400
        update_job(job_id, title="Pictures")
        threading.Thread(target=_download_image_list, args=(job_id, url, safe_items), daemon=True).start()
    elif kind == "image":
        threading.Thread(target=_image_worker, args=(job_id, url), daemon=True).start()
    else:
        threading.Thread(target=_special_video_worker, args=(job_id, url, quality), daemon=True).start()
    return jsonify({"success": True, "job_id": job_id, "status": "queued"})
