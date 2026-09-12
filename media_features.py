import shutil
import threading
import time
import urllib.request
import uuid
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from flask import jsonify, request

from core_app import (
    app,
    DOWNLOAD_DIR,
    TEMP_DIR,
    extractor_options,
    get_job,
    jobs,
    jobs_lock,
    make_progress_hook,
    unique_output_path,
    update_job,
)


def _new_job(url, kind, quality=720):
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


def _special_video_worker(job_id, url, quality):
    job_dir = TEMP_DIR / f"special_{job_id}"
    job_dir.mkdir(parents=True, exist_ok=True)
    started_at = time.time()
    update_job(job_id, status="starting", started_at=started_at, worker_running=True)

    try:
        options = extractor_options()
        options.update({
            "format": (
                f"bv*[height<={int(quality)}][ext=mp4]+ba[ext=m4a]/"
                f"bv*[height<={int(quality)}]+ba/"
                f"b[height<={int(quality)}][ext=mp4]/b"
            ),
            "outtmpl": str(job_dir / "%(title)s.%(ext)s"),
            "merge_output_format": "mp4",
            "progress_hooks": [make_progress_hook(job_id)],
            "postprocessors": [],
        })

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)

        title = info.get("title") or "video"
        update_job(job_id, title=title)
        files = [
            p for p in job_dir.iterdir()
            if p.is_file() and not p.name.endswith(".part")
        ]
        if not files:
            raise RuntimeError("No video file was produced.")

        output = max(files, key=lambda p: p.stat().st_size)
        final_path = unique_output_path(title, "mp4")
        shutil.move(str(output), str(final_path))
        _finish_job(job_id, final_path, started_at)

    except Exception as error:
        update_job(
            job_id,
            status="error",
            error=str(error),
            worker_running=False,
            finished_at=time.time(),
            conversion=False,
        )
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


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
        thumbnails = info.get("thumbnails") or []
        thumbnails = [t for t in thumbnails if t.get("url")]
        image_url = info.get("thumbnail") or (thumbnails[-1]["url"] if thumbnails else None)
        if not image_url:
            raise RuntimeError("No downloadable image was found for this post.")

        ext = (thumbnails[-1].get("ext") if thumbnails else None) or "jpg"
        if ext not in ("jpg", "jpeg", "png", "webp"):
            ext = "jpg"
        temp_file = job_dir / f"image.{ext}"

        urllib.request.urlretrieve(image_url, temp_file)
        final_path = unique_output_path(title, ext)
        shutil.move(str(temp_file), str(final_path))
        _finish_job(job_id, final_path, started_at)

    except Exception as error:
        update_job(
            job_id,
            status="error",
            error=str(error),
            worker_running=False,
            finished_at=time.time(),
            conversion=False,
        )
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def _allowed_special_url(url):
    domain = urlparse(url).netloc.lower().removeprefix("www.")
    return "tiktok.com" in domain or "pinterest." in domain


@app.post("/api/special-download")
def special_download():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    kind = (data.get("kind") or "video").lower()

    try:
        quality = int(data.get("quality", 720))
    except Exception:
        quality = 720
    quality = max(144, min(2160, quality))

    if not url:
        return jsonify({"error": "URL is required."}), 400
    if not _allowed_special_url(url):
        return jsonify({"error": "This special mode supports TikTok and Pinterest URLs."}), 400
    if kind not in ("video", "image"):
        kind = "video"

    job_id = _new_job(url, kind, quality)
    target = _image_worker if kind == "image" else _special_video_worker
    args = (job_id, url) if kind == "image" else (job_id, url, quality)
    threading.Thread(target=target, args=args, daemon=True).start()

    return jsonify({"success": True, "job_id": job_id, "status": "queued"})
