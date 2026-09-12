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
from flask import jsonify, request

from core_app import (
    app,
    TEMP_DIR,
    extractor_options,
    jobs,
    jobs_lock,
    make_progress_hook,
    unique_output_path,
    update_job,
    ffmpeg_available,
)


def _new_job(url, kind, quality=2160):
    job_id = uuid.uuid4().hex
    with jobs_lock:
        jobs[job_id] = {
            "id": job_id,
            "url": url,
            "domain": urlparse(url).netloc.lower(),
            "mode": kind,
            "quality": quality,
            "status": "queued",
            "title": "Preparing download...",
            "filename": None,
            "download_url": None,
            "percentage": 0,
            "downloaded_bytes": 0,
            "total_bytes": 0,
            "filesize": None,
            "speed": 0,
            "eta": None,
            "elapsed": 0,
            "error": None,
            "paused": False,
            "cancel_requested": False,
            "started_at": None,
            "finished_at": None,
            "worker_running": False,
            "source_height": None,
            "target_height": quality,
            "conversion": False,
        }
    return job_id


def _finish_job(job_id, final_path, started_at):
    if not final_path.exists() or final_path.stat().st_size <= 0:
        raise RuntimeError("The final media file was not created correctly.")
    size = final_path.stat().st_size
    elapsed = max(time.time() - (started_at or time.time()), 0.001)
    update_job(
        job_id,
        status="completed",
        percentage=100,
        downloaded_bytes=size,
        total_bytes=size,
        filesize=size,
        filename=final_path.name,
        download_url=f"/api/file/{final_path.name}",
        elapsed=elapsed,
        speed=size / elapsed,
        eta=0,
        finished_at=time.time(),
        worker_running=False,
        conversion=False,
    )


def _choose_video_format(info, quality):
    """Prefer a ready-made MP4 with audio; merge only when necessary."""
    limit = int(quality)
    formats = info.get("formats") or []

    combined_mp4 = [
        f for f in formats
        if f.get("vcodec") not in (None, "none")
        and f.get("acodec") not in (None, "none")
        and f.get("height")
        and int(f.get("height") or 0) <= limit
        and f.get("ext") == "mp4"
    ]
    combined_mp4.sort(key=lambda f: (int(f.get("height") or 0), f.get("tbr") or 0), reverse=True)
    if combined_mp4:
        return str(combined_mp4[0].get("format_id")), False

    if not ffmpeg_available():
        combined_any = [
            f for f in formats
            if f.get("vcodec") not in (None, "none")
            and f.get("acodec") not in (None, "none")
            and f.get("height")
            and int(f.get("height") or 0) <= limit
        ]
        combined_any.sort(key=lambda f: (int(f.get("height") or 0), f.get("tbr") or 0), reverse=True)
        if combined_any:
            return str(combined_any[0].get("format_id")), False
        raise RuntimeError("This video needs FFmpeg to merge video and audio, but FFmpeg is not available.")

    # yt-dlp's documented bv+ba selector is used for separate streams.
    return f"bv*[height<={limit}]+ba/b[height<={limit}]", True


def _special_video_worker(job_id, url, quality):
    job_dir = TEMP_DIR / f"special_{job_id}"
    job_dir.mkdir(parents=True, exist_ok=True)
    started_at = time.time()
    update_job(job_id, status="starting", started_at=started_at, worker_running=True)

    try:
        with yt_dlp.YoutubeDL(extractor_options()) as ydl:
            info = ydl.extract_info(url, download=False)

        title = info.get("title") or "video"
        update_job(job_id, title=title, source_height=info.get("height"))

        format_selector, needs_merge = _choose_video_format(info, quality)
        options = extractor_options()
        options.update({
            "format": format_selector,
            "outtmpl": str(job_dir / "%(title)s.%(ext)s"),
            "merge_output_format": "mp4",
            "progress_hooks": [make_progress_hook(job_id)],
            "noplaylist": True,
            "retries": 8,
            "fragment_retries": 8,
            "file_access_retries": 8,
        })
        if not needs_merge:
            # A ready-made MP4 already contains audio, so no conversion/merge step is needed.
            options.pop("merge_output_format", None)

        update_job(job_id, status="downloading")
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)

        update_job(job_id, title=info.get("title") or title)
        files = [
            p for p in job_dir.iterdir()
            if p.is_file() and not p.name.endswith((".part", ".ytdl"))
        ]
        if not files:
            raise RuntimeError("Download completed, but no final video file was produced.")

        # Prefer the final mp4; never select a tiny metadata/sidecar file.
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


def _image_url_candidates(info):
    candidates = []
    primary = info.get("thumbnail")
    if primary:
        candidates.append(primary)
    for item in sorted(info.get("thumbnails") or [], key=lambda x: (x.get("width") or 0, x.get("height") or 0), reverse=True):
        if item.get("url") and item["url"] not in candidates:
            candidates.append(item["url"])
    return candidates


def _download_image(url, source_url, destination):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Referer": source_url,
    }
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response, open(destination, "wb") as output:
        shutil.copyfileobj(response, output)


def _image_worker(job_id, url):
    job_dir = TEMP_DIR / f"image_{job_id}"
    job_dir.mkdir(parents=True, exist_ok=True)
    started_at = time.time()
    update_job(job_id, status="starting", started_at=started_at, worker_running=True)

    try:
        options = extractor_options()
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)

        title = info.get("title") or "image"
        update_job(job_id, title=title)
        candidates = _image_url_candidates(info)
        if not candidates:
            raise RuntimeError("No downloadable picture was found for this post.")

        last_error = None
        temp_file = None
        for index, image_url in enumerate(candidates[:8]):
            try:
                guessed = Path(urlparse(image_url).path).suffix.lower()
                if guessed not in (".jpg", ".jpeg", ".png", ".webp"):
                    guessed = ".jpg"
                candidate_file = job_dir / f"image_{index}{guessed}"
                _download_image(image_url, url, candidate_file)
                if candidate_file.stat().st_size > 0:
                    temp_file = candidate_file
                    break
            except (OSError, urllib.error.URLError, ValueError) as error:
                last_error = error

        if temp_file is None:
            raise RuntimeError(f"Picture download failed: {last_error or 'image server rejected the request.'}")

        extension = temp_file.suffix.lstrip(".") or "jpg"
        final_path = unique_output_path(title, extension)
        shutil.move(str(temp_file), str(final_path))
        _finish_job(job_id, final_path, started_at)

    except Exception as error:
        update_job(job_id, status="error", error=str(error), worker_running=False, finished_at=time.time(), conversion=False)
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def _allowed_special_url(url):
    domain = urlparse(url).netloc.lower().removeprefix("www.")
    return domain == "tiktok.com" or domain.endswith(".tiktok.com") or domain == "pinterest.com" or domain.endswith(".pinterest.com") or domain.endswith(".pinterest.co.uk") or domain.endswith(".pinterest.de") or domain.endswith(".pinterest.fr")


@app.post("/api/special-download")
def special_download():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    kind = (data.get("kind") or "video").lower()

    try:
        quality = int(data.get("quality", 2160))
    except Exception:
        quality = 2160
    quality = max(144, min(2160, quality))

    if not url:
        return jsonify({"error": "URL is required."}), 400
    if not _allowed_special_url(url):
        return jsonify({"error": "This focused tool supports TikTok and Pinterest public URLs."}), 400
    if kind not in ("video", "image"):
        kind = "video"

    job_id = _new_job(url, kind, quality)
    target = _image_worker if kind == "image" else _special_video_worker
    args = (job_id, url) if kind == "image" else (job_id, url, quality)
    threading.Thread(target=target, args=args, daemon=True).start()
    return jsonify({"success": True, "job_id": job_id, "status": "queued"})
