from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp
import re
import uuid
import threading
import time
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
TEMP_DIR = BASE_DIR / "temp_downloads"

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

jobs = {}
jobs_lock = threading.Lock()


class PauseDownload(Exception):
    pass


def safe_filename(name):
    name = name or "video"
    name = re.sub(r'[\\/:*?"<>|]+', "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name.rstrip(". ")
    if not name:
        name = "video"
    return name[:180]


def format_bytes(value):
    if value is None:
        return "Unknown"
    try:
        value = float(value)
    except Exception:
        return "Unknown"
    if value < 0:
        return "Unknown"
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while value >= 1024 and i < len(units) - 1:
        value /= 1024
        i += 1
    if i == 0:
        return f"{int(value)} {units[i]}"
    return f"{value:.2f} {units[i]}"


def format_seconds(seconds):
    if seconds is None:
        return None
    try:
        seconds = int(seconds)
    except Exception:
        return None
    if seconds < 0:
        return None
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def get_domain(url):
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        return ""


def ffmpeg_available():
    return shutil.which("ffmpeg") is not None


def extractor_options():
    return {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 5,
        "fragment_retries": 5,
        "file_access_retries": 5,
        "continuedl": True,
        "nopart": False,
        "overwrites": False,
        "restrictfilenames": False,
        "windowsfilenames": True,
    }


def create_job(url, mode, quality):
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id, "url": url, "domain": get_domain(url), "mode": mode, "quality": quality,
        "status": "queued", "title": "Preparing download...", "filename": None, "download_url": None,
        "percentage": 0, "downloaded_bytes": 0, "total_bytes": 0, "filesize": None,
        "speed": 0, "eta": None, "elapsed": 0, "error": None, "paused": False, "cancel_requested": False,
        "started_at": None, "finished_at": None, "worker_running": False, "source_height": None,
        "target_height": quality, "conversion": False,
    }
    with jobs_lock:
        jobs[job_id] = job
    return job_id


def update_job(job_id, **values):
    with jobs_lock:
        if job_id in jobs:
            jobs[job_id].update(values)


def get_job(job_id):
    with jobs_lock:
        if job_id not in jobs:
            return None
        return dict(jobs[job_id])


def get_format_size(fmt):
    return fmt.get("filesize") or fmt.get("filesize_approx") or 0


def get_video_formats(info):
    result = []
    for fmt in info.get("formats", []):
        height = fmt.get("height")
        vcodec = fmt.get("vcodec")
        if not height or not vcodec or vcodec == "none":
            continue
        try:
            height = int(height)
        except Exception:
            continue
        result.append(fmt)
    return result


def get_available_heights(info):
    heights = set()
    for fmt in get_video_formats(info):
        if fmt.get("height"):
            heights.add(int(fmt["height"]))
    return sorted(heights, reverse=True)


def choose_source_format(info, target_height):
    formats = get_video_formats(info)
    if not formats:
        return None
    heights = sorted({int(f["height"]) for f in formats if f.get("height")})
    if not heights or target_height > max(heights):
        return None
    suitable = [h for h in heights if h >= target_height]
    chosen_height = min(suitable) if suitable else max(heights)
    candidates = [f for f in formats if int(f.get("height")) == chosen_height]
    candidates.sort(key=lambda f: (1 if get_format_size(f) else 0, f.get("tbr") or 0, f.get("fps") or 0), reverse=True)
    return candidates[0]


def choose_audio_format(info):
    audio_formats = []
    for fmt in info.get("formats", []):
        acodec = fmt.get("acodec")
        if not acodec or acodec == "none":
            continue
        audio_formats.append(fmt)
    if not audio_formats:
        return None
    audio_formats.sort(key=lambda f: (f.get("abr") or 0, get_format_size(f)), reverse=True)
    return audio_formats[0]


def make_progress_hook(job_id):
    def hook(data):
        job = get_job(job_id)
        if not job:
            return
        if job.get("cancel_requested"):
            raise yt_dlp.utils.DownloadError("Download cancelled by user.")
        if job.get("paused"):
            raise PauseDownload("Download paused.")
        status = data.get("status")
        if status == "downloading":
            downloaded = data.get("downloaded_bytes") or 0
            total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
            speed = data.get("speed") or 0
            eta = data.get("eta")
            percentage = max(0, min(100, (downloaded / total) * 100)) if total > 0 else 0
            started_at = job.get("started_at") or time.time()
            elapsed = time.time() - started_at
            update_job(job_id, status="downloading", downloaded_bytes=downloaded, total_bytes=total,
                       percentage=percentage, speed=speed, eta=eta, elapsed=elapsed,
                       filesize=total or job.get("filesize"))
        elif status == "finished":
            downloaded = data.get("downloaded_bytes") or data.get("total_bytes") or 0
            update_job(job_id, percentage=100, downloaded_bytes=downloaded,
                       total_bytes=data.get("total_bytes") or downloaded, status="processing")
    return hook


def unique_output_path(title, extension):
    clean_title = safe_filename(title)
    extension = extension.lstrip(".")
    candidate = DOWNLOAD_DIR / f"{clean_title}.{extension}"
    if not candidate.exists():
        return candidate
    counter = 1
    while True:
        candidate = DOWNLOAD_DIR / f"{clean_title} ({counter}).{extension}"
        if not candidate.exists():
            return candidate
        counter += 1


def resize_video(input_file, output_file, target_height, job_id):
    if not ffmpeg_available():
        raise RuntimeError("FFmpeg is required for quality conversion.")
    update_job(job_id, status="converting", conversion=True, percentage=0)
    # Never upscale: selected quality is the maximum output height.
    # When the source is larger, the result is exactly the requested height.
    scale_filter = f"scale=-2:min({int(target_height)},ih)"
    command = ["ffmpeg", "-y", "-i", str(input_file), "-vf", scale_filter,
               "-c:v", "libx264", "-crf", "28", "-preset", "medium",
               "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(output_file)]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", errors="replace")
    _, stderr = process.communicate()
    if process.returncode != 0:
        raise RuntimeError("FFmpeg conversion failed: " + stderr[-1500:])


# =========================================================
# DOWNLOAD WORKER
# =========================================================
def download_worker(job_id, url, mode, quality):
    job_dir = TEMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    update_job(job_id, status="starting", started_at=time.time(), worker_running=True)
    try:
        with yt_dlp.YoutubeDL(extractor_options()) as ydl:
            info = ydl.extract_info(url, download=False)
        title = info.get("title", "video")
        update_job(job_id, title=title)
        if mode == "audio":
            format_selector = "bestaudio/best"
            options = extractor_options()
            options.update({"format": format_selector, "outtmpl": str(job_dir / "%(title)s.%(ext)s"),
                            "progress_hooks": [make_progress_hook(job_id)], "postprocessors": [
                                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]})
            with yt_dlp.YoutubeDL(options) as ydl:
                downloaded = ydl.extract_info(url, download=True)
            files = [p for p in job_dir.iterdir() if p.is_file() and not p.name.endswith(".part")]
            if not files:
                raise RuntimeError("No audio file was produced.")
            output = max(files, key=lambda p: p.stat().st_size)
            final = unique_output_path(downloaded.get("title") or title, "mp3")
            shutil.move(str(output), str(final))
            size = final.stat().st_size
            elapsed = max(time.time() - job.get("started_at", time.time()), 0.001)
            update_job(job_id, status="completed", percentage=100, downloaded_bytes=size, total_bytes=size,
                       filesize=size, filename=final.name, download_url=f"/api/file/{final.name}", eta=0,
                       speed=size / elapsed, elapsed=elapsed, finished_at=time.time(), worker_running=False)
            return
        source = choose_source_format(info, int(quality))
        if not source:
            raise RuntimeError(f"{int(quality)}p is not available for this source.")
        selector = str(source.get("format_id"))
        if str(source.get("acodec") or "none") == "none":
            selector = f"{selector}+bestaudio/{selector}"
        options = extractor_options()
        options.update({"format": selector, "outtmpl": str(job_dir / "%(title)s.%(ext)s"),
                        "merge_output_format": "mp4", "progress_hooks": [make_progress_hook(job_id)]})
        update_job(job_id, status="downloading", source_height=int(source.get("height") or 0))
        with yt_dlp.YoutubeDL(options) as ydl:
            downloaded = ydl.extract_info(url, download=True)
        files = [p for p in job_dir.iterdir() if p.is_file() and not p.name.endswith((".part", ".ytdl"))]
        if not files:
            raise RuntimeError("Download completed, but no final video file was produced.")
        output = max([p for p in files if p.suffix.lower() == ".mp4"] or files, key=lambda p: p.stat().st_size)
        if int(source.get("height") or 0) > int(quality):
            converted = job_dir / "converted.mp4"
            resize_video(output, converted, int(quality), job_id)
            output = converted
        final = unique_output_path(downloaded.get("title") or title, "mp4")
        shutil.move(str(output), str(final))
        size = final.stat().st_size
        elapsed = max(time.time() - (get_job(job_id) or {}).get("started_at", time.time()), 0.001)
        update_job(job_id, status="completed", percentage=100, downloaded_bytes=size, total_bytes=size,
                   filesize=size, filename=final.name, download_url=f"/api/file/{final.name}", eta=0,
                   speed=size / elapsed, elapsed=elapsed, finished_at=time.time(), worker_running=False, conversion=False)
    except PauseDownload:
        update_job(job_id, status="paused", worker_running=False)
    except Exception as error:
        update_job(job_id, status="error", error=str(error), worker_running=False, finished_at=time.time(), conversion=False)
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/job/<job_id>")
def job_status(job_id):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found."}), 404
    return jsonify(job)


@app.post("/api/download")
def start_download():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    mode = (data.get("mode") or "video").lower()
    try:
        quality = max(144, min(2160, int(data.get("quality", 1080))))
    except Exception:
        quality = 1080
    if not url:
        return jsonify({"error": "URL is required."}), 400
    job_id = create_job(url, mode, quality)
    thread = threading.Thread(target=download_worker, args=(job_id, url, mode, quality), daemon=True)
    thread.start()
    return jsonify({"success": True, "job_id": job_id, "status": "queued"})


@app.get("/api/file/<path:filename>")
def download_file(filename):
    target = (DOWNLOAD_DIR / filename).resolve()
    base = DOWNLOAD_DIR.resolve()
    if target != base and base not in target.parents:
        return jsonify({"error": "Invalid file path."}), 400
    if not target.is_file():
        return jsonify({"error": "File not found."}), 404
    return send_file(target, as_attachment=True, download_name=target.name)


@app.post("/api/job/<job_id>/pause")
def pause_job(job_id):
    update_job(job_id, paused=True)
    return jsonify({"success": True})


@app.post("/api/job/<job_id>/resume")
def resume_job(job_id):
    update_job(job_id, paused=False)
    return jsonify({"success": True})


@app.post("/api/job/<job_id>/cancel")
def cancel_job(job_id):
    update_job(job_id, cancel_requested=True)
    return jsonify({"success": True})
