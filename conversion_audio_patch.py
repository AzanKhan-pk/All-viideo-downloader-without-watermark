"""Focused fixes for FFmpeg conversion progress and Pinterest video audio."""

import shutil
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import core_app
import media_features
import yt_dlp


def _probe_duration(path):
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        value = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        return float(value) if value else 0.0
    except Exception:
        return 0.0


def _run_ffmpeg_resize(input_file, output_file, target_height, job_id):
    if not core_app.ffmpeg_available():
        raise RuntimeError("FFmpeg is required for quality conversion.")

    input_file = Path(input_file)
    output_file = Path(output_file)
    duration = _probe_duration(input_file)
    core_app.update_job(job_id, status="converting", conversion=True, percentage=0, eta=None)

    scale_filter = f"scale=-2:min({int(target_height)},ih)"
    command = [
        "ffmpeg", "-y", "-nostdin", "-i", str(input_file), "-vf", scale_filter,
        "-c:v", "libx264", "-crf", "28", "-preset", "medium",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats", "-stats_period", "0.5", str(output_file),
    ]

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )

    stderr_lines = []

    def drain_stderr():
        if process.stderr is None:
            return
        for line in process.stderr:
            if len(stderr_lines) >= 80:
                stderr_lines.pop(0)
            stderr_lines.append(line.rstrip())

    stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
    stderr_thread.start()

    try:
        if process.stdout is not None:
            for line in process.stdout:
                line = line.strip()
                if not line or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key not in ("out_time_us", "out_time_ms", "speed", "progress"):
                    continue
                if key in ("out_time_us", "out_time_ms") and duration > 0:
                    try:
                        # FFmpeg's out_time_us is microseconds; older builds may only expose out_time_ms.
                        elapsed_output = float(value) / 1_000_000.0
                        percent = max(0.0, min(99.0, elapsed_output / duration * 100.0))
                        core_app.update_job(job_id, status="converting", conversion=True, percentage=percent)
                    except (TypeError, ValueError):
                        pass
                elif key == "progress" and value == "end":
                    core_app.update_job(job_id, status="converting", conversion=True, percentage=99.5)
    finally:
        process.wait()
        stderr_thread.join(timeout=2)

    if process.returncode != 0 or not output_file.exists() or output_file.stat().st_size <= 0:
        detail = "\n".join(stderr_lines[-20:])
        raise RuntimeError("FFmpeg quality conversion failed." + (f" {detail[-1200:]}" if detail else ""))

    core_app.update_job(job_id, status="converting", conversion=True, percentage=99.8)


# This replaces the original blocking conversion so the UI receives live FFmpeg progress.
core_app.resize_video = _run_ffmpeg_resize

# media_resilience_patch installs its own safe resize function. Replace that too so
# Pinterest/TikTok fallback conversions use the same progress-aware implementation.
try:
    import media_resilience_patch
    media_resilience_patch._safe_resize = _run_ffmpeg_resize
    core_app.resize_video = _run_ffmpeg_resize
except Exception:
    pass


_original_special_video_worker = media_features._special_direct_video_worker


def _try_pinterest_ytdlp(job_id, url, info, quality):
    """Prefer yt-dlp's normal video+audio merge for Pinterest when available."""
    host = urlparse(url).netloc.lower().removeprefix("www.")
    if "pinterest." not in host:
        return False

    job_dir = core_app.TEMP_DIR / f"pinterest_merge_{job_id}"
    job_dir.mkdir(parents=True, exist_ok=True)
    started_at = time.time()
    try:
        title = info.get("title") or "Pinterest video"
        options = media_features._options(url)
        options.update({
            "format": "bv*+ba/b",
            "outtmpl": str(job_dir / "%(title)s.%(ext)s"),
            "merge_output_format": "mp4",
            "progress_hooks": [core_app.make_progress_hook(job_id)],
            "noplaylist": True,
            "retries": 10,
            "fragment_retries": 10,
            "file_access_retries": 10,
        })
        core_app.update_job(job_id, title=title, status="downloading", started_at=started_at, worker_running=True)
        with yt_dlp.YoutubeDL(options) as ydl:
            downloaded = ydl.extract_info(url, download=True)

        files = [
            p for p in job_dir.iterdir()
            if p.is_file() and not p.name.endswith((".part", ".ytdl"))
        ]
        if not files:
            return False
        output = max(files, key=lambda p: p.stat().st_size)
        final = core_app.unique_output_path(downloaded.get("title") or title, "mp4")
        shutil.move(str(output), str(final))
        media_features._finish_job(job_id, final, started_at)
        return True
    except Exception as error:
        print(f"[{job_id}] Pinterest audio merge fallback: {error}")
        return False
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def _special_direct_video_worker(job_id, url, info, quality):
    # Pinterest fallback URLs can be video-only. Give the normal yt-dlp extractor
    # one focused chance to obtain and mux the separate audio stream before using
    # the existing direct-media fallback.
    if _try_pinterest_ytdlp(job_id, url, info, quality):
        return
    return _original_special_video_worker(job_id, url, info, quality)


media_features._special_direct_video_worker = _special_direct_video_worker
