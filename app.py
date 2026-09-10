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

try:
    from curl_cffi import requests as curl_requests
except Exception:
    curl_requests = None

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


# =========================================================
# BASIC HELPERS
# =========================================================

def safe_filename(name):
    name = name or "video"

    name = re.sub(
        r'[\\/:*?"<>|]+',
        "_",
        name
    )

    name = re.sub(
        r"\s+",
        " ",
        name
    ).strip()

    name = name.rstrip(". ")

    if not name:
        name = "video"

    # Windows path limit safety
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
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 5,
        "extractor_retries": 4,
        "fragment_retries": 5,
        "file_access_retries": 5,
        "continuedl": True,
        "nopart": False,
        "overwrites": False,
        "restrictfilenames": False,
        "windowsfilenames": True,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/",
        },
    }
    # curl_cffi 0.15.x is used by the Windows build for stable browser
    # impersonation. Do not force impersonation when the optional handler is
    # unavailable; yt-dlp can then fall back to its normal request handlers.
    if curl_requests is not None:
        options["impersonate"] = "chrome"
    return options


# =========================================================
# JOBS
# =========================================================\n\ndef is_tiktok_url(url):\n    domain = get_domain(url)\n    return domain == "tiktok.com" or domain.endswith(".tiktok.com")\n\n\ndef _script_json(html, script_id):\n    match = re.search(\n        rf'<script[^>]+id=["\\\']{re.escape(script_id)}["\\\'][^>]*>(.*?)</script>',\n        html,\n        re.S | re.I,\n    )\n    if not match:\n        return None\n    try:\n        import html as html_module\n        raw = html_module.unescape(match.group(1).strip())\n        return __import__("json").loads(raw)\n    except Exception:\n        return None\n\n\ndef tiktok_web_fallback(url):\n    """Extract public TikTok page data when the normal yt-dlp webpage parser fails."""\n    if not is_tiktok_url(url) or curl_requests is None:\n        return None\n\n    headers = {\n        "User-Agent": (\n            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "\n            "AppleWebKit/537.36 (KHTML, like Gecko) "\n            "Chrome/140.0.0.0 Safari/537.36"\n        ),\n        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",\n        "Accept-Language": "en-US,en;q=0.9",\n        "Referer": "https://www.tiktok.com/",\n    }\n\n    session = curl_requests.Session(impersonate="chrome")\n    response = session.get(url, headers=headers, timeout=30, allow_redirects=True)\n    response.raise_for_status()\n    html = response.text\n\n    item = None\n    sigi = _script_json(html, "SIGI_STATE")\n    if isinstance(sigi, dict):\n        item_module = sigi.get("ItemModule") or {}\n        for value in item_module.values():\n            if isinstance(value, dict) and isinstance(value.get("video"), dict):\n                item = value\n                break\n\n    if item is None:\n        universal = _script_json(html, "__UNIVERSAL_DATA_FOR_REHYDRATION__")\n        scope = universal.get("__DEFAULT_SCOPE__", {}) if isinstance(universal, dict) else {}\n        detail = scope.get("webapp.video-detail", {}) if isinstance(scope, dict) else {}\n        item = ((detail.get("itemInfo") or {}).get("itemStruct") if isinstance(detail, dict) else None)\n\n    if not isinstance(item, dict):\n        return None\n\n    video = item.get("video") or {}\n    formats = []\n\n    bitrate_items = video.get("bitrateInfo") or []\n    for index, entry in enumerate(bitrate_items):\n        if not isinstance(entry, dict):\n            continue\n        play = entry.get("PlayAddr") or entry.get("playAddr") or {}\n        urls = play.get("UrlList") or play.get("urlList") or []\n        if not urls:\n            continue\n        direct = urls[-1]\n        height = entry.get("Height") or entry.get("height") or play.get("Height") or play.get("height") or video.get("height")\n        width = entry.get("Width") or entry.get("width") or play.get("Width") or play.get("width") or video.get("width")\n        bitrate = entry.get("Bitrate") or entry.get("bitrate") or 0\n        try:\n            height = int(height) if height else None\n        except Exception:\n            height = None\n        try:\n            width = int(width) if width else None\n        except Exception:\n            width = None\n        formats.append({\n            "format_id": f"tiktok-web-{index}",\n            "url": direct,\n            "ext": "mp4",\n            "height": height,\n            "width": width,\n            "vcodec": "h264",\n            "acodec": "aac",\n            "tbr": (float(bitrate) / 1000.0) if bitrate else None,\n            "filesize": None,\n        })\n\n    if not formats:\n        direct = video.get("downloadAddr") or video.get("download_addr") or video.get("playAddr") or video.get("play_addr")\n        if isinstance(direct, dict):\n            urls = direct.get("UrlList") or direct.get("urlList") or []\n            direct = urls[-1] if urls else None\n        if direct:\n            formats.append({\n                "format_id": "tiktok-web-direct",\n                "url": direct,\n                "ext": "mp4",\n                "height": video.get("height"),\n                "width": video.get("width"),\n                "vcodec": "h264",\n                "acodec": "aac",\n                "filesize": None,\n            })\n\n    if not formats:\n        return None\n\n    formats.sort(key=lambda f: (f.get("height") or 0, f.get("tbr") or 0), reverse=True)\n    video_id = str(item.get("id") or "tiktok")\n    title = item.get("desc") or item.get("description") or f"TikTok video {video_id}"\n    author = item.get("author") or {}\n    thumbnail = video.get("cover") or video.get("originCover") or video.get("dynamicCover")\n    return {\n        "id": video_id,\n        "title": title,\n        "thumbnail": thumbnail,\n        "duration": item.get("video", {}).get("duration"),\n        "uploader": author.get("uniqueId") if isinstance(author, dict) else author,\n        "extractor": "TikTok",\n        "extractor_key": "TikTok",\n        "domain": "tiktok.com",\n        "webpage_url": response.url,\n        "formats": formats,\n        "_avd_tiktok_fallback": True,\n    }\n\n\ndef extract_media_info(url):\n    try:\n        with yt_dlp.YoutubeDL(extractor_options()) as ydl:\n            return ydl.extract_info(url, download=False)\n    except Exception:\n        fallback = tiktok_web_fallback(url)\n        if fallback:\n            return fallback\n        raise\n\n\ndef has_audio_stream(path):\n    if not ffmpeg_available():\n        return True\n    ffprobe = shutil.which("ffprobe")\n    if not ffprobe:\n        return True\n    try:\n        result = subprocess.run(\n            [ffprobe, "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],\n            capture_output=True, text=True, timeout=20, encoding="utf-8", errors="replace",\n        )\n        return bool(result.stdout.strip())\n    except Exception:\n        return True\n\n\ndef create_job(url, mode, quality):

    job_id = uuid.uuid4().hex

    job = {
        "id": job_id,
        "url": url,
        "domain": get_domain(url),
        "mode": mode,
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


# =========================================================
# FORMAT ANALYSIS
# =========================================================

def get_format_size(fmt):
    return (
        fmt.get("filesize")
        or fmt.get("filesize_approx")
        or 0
    )


def get_video_formats(info):

    result = []

    for fmt in info.get("formats", []):

        height = fmt.get("height")
        vcodec = fmt.get("vcodec")

        if not height:
            continue

        if not vcodec or vcodec == "none":
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

        height = fmt.get("height")

        if height:
            heights.add(int(height))

    return sorted(
        heights,
        reverse=True
    )


def choose_source_format(info, target_height):

    """
    Choose the smallest available source resolution that is
    >= requested target.

    Example:

        Available:
        360, 720, 1080

        User:
        144

        Selected source:
        360

    Then FFmpeg converts 360 -> 144.

    If target is exactly available, it uses that resolution.

    If target is higher than the source maximum, returns None.
    """

    formats = get_video_formats(info)

    if not formats:
        return None

    # Group formats by resolution.
    heights = sorted(
        set(
            int(f["height"])
            for f in formats
            if f.get("height")
        )
    )

    if not heights:
        return None

    # Cannot create genuine higher resolution without
    # upscaling/faking it.
    max_height = max(heights)

    if target_height > max_height:
        return None

    # Smallest real source resolution >= target.
    suitable_heights = [
        h for h in heights
        if h >= target_height
    ]

    if suitable_heights:
        chosen_height = min(
            suitable_heights
        )
    else:
        chosen_height = max_height

    candidates = [
        f
        for f in formats
        if int(f.get("height")) == chosen_height
    ]

    # Prefer formats with actual filesize metadata,
    # then bitrate, then fps.
    candidates.sort(
        key=lambda f: (
            1 if get_format_size(f) else 0,
            f.get("tbr") or 0,
            f.get("fps") or 0
        ),
        reverse=True
    )

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

    audio_formats.sort(
        key=lambda f: (
            f.get("abr") or 0,
            get_format_size(f)
        ),
        reverse=True
    )

    return audio_formats[0]


# =========================================================
# PROGRESS
# =========================================================

def make_progress_hook(job_id):

    def hook(data):

        job = get_job(job_id)

        if not job:
            return

        if job.get("cancel_requested"):

            raise yt_dlp.utils.DownloadError(
                "Download cancelled by user."
            )

        if job.get("paused"):

            raise PauseDownload(
                "Download paused."
            )

        status = data.get("status")

        if status == "downloading":

            downloaded = (
                data.get("downloaded_bytes")
                or 0
            )

            total = (
                data.get("total_bytes")
                or data.get("total_bytes_estimate")
                or 0
            )

            speed = (
                data.get("speed")
                or 0
            )

            eta = data.get("eta")

            percentage = 0

            if total > 0:

                percentage = (
                    downloaded / total
                ) * 100

                percentage = max(
                    0,
                    min(100, percentage)
                )

            started_at = (
                job.get("started_at")
                or time.time()
            )

            elapsed = (
                time.time() -
                started_at
            )

            update_job(

                job_id,

                status="downloading",

                downloaded_bytes=
                    downloaded,

                total_bytes=
                    total,

                percentage=
                    percentage,

                speed=
                    speed,

                eta=
                    eta,

                elapsed=
                    elapsed,

                filesize=
                    total or job.get(
                        "filesize"
                    )
            )

        elif status == "finished":

            downloaded = (
                data.get(
                    "downloaded_bytes"
                )
                or
                data.get(
                    "total_bytes"
                )
                or
                0
            )

            update_job(

                job_id,

                percentage=100,

                downloaded_bytes=
                    downloaded,

                total_bytes=
                    data.get(
                        "total_bytes"
                    )
                    or
                    downloaded,

                status="processing"
            )

    return hook


# =========================================================
# FINAL FILE NAME
# =========================================================

def unique_output_path(title, extension):

    clean_title = safe_filename(
        title
    )

    extension = extension.lstrip(".")

    candidate = (
        DOWNLOAD_DIR /
        f"{clean_title}.{extension}"
    )

    if not candidate.exists():
        return candidate

    counter = 1

    while True:

        candidate = (
            DOWNLOAD_DIR /
            f"{clean_title} ({counter}).{extension}"
        )

        if not candidate.exists():
            return candidate

        counter += 1


# =========================================================
# FFMPEG RESIZE
# =========================================================

def resize_video(
    input_file,
    output_file,
    target_height,
    job_id
):

    if not ffmpeg_available():

        raise RuntimeError(
            "FFmpeg is required for quality conversion."
        )

    update_job(
        job_id,
        status="converting",
        conversion=True,
        percentage=0
    )

    # -2 keeps aspect ratio and makes width divisible by 2.
    scale_filter = (
        f"scale=-2:{int(target_height)}"
    )

    command = [

        "ffmpeg",

        "-y",

        "-i",
        str(input_file),

        "-vf",
        scale_filter,

        # H.264 MP4
        "-c:v",
        "libx264",

        # Reasonable compression for lower resolutions.
        "-crf",
        "28",

        "-preset",
        "medium",

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        "-movflags",
        "+faststart",

        str(output_file)
    ]

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    _, stderr = process.communicate()

    if process.returncode != 0:

        raise RuntimeError(
            "FFmpeg conversion failed: "
            + stderr[-1500:]
        )


# =========================================================
# DOWNLOAD WORKER
# =========================================================

def download_worker(
    job_id,
    url,
    mode,
    quality
):

    job_dir = (
        TEMP_DIR /
        job_id
    )

    job_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    update_job(

        job_id,

        status="starting",

        started_at=time.time(),

        worker_running=True

    )

    try:

        # =================================================
        # FIRST EXTRACTION
        # =================================================

        with yt_dlp.YoutubeDL(
            extractor_options()
        ) as ydl:

            info = extract_media_info(url)

        title = info.get(
            "title",
            "video"
        )

        update_job(
            job_id,
            title=title
        )

        # =================================================
        # AUDIO MODE
        # =================================================

        if mode == "audio":

            format_selector = (
                "bestaudio/best"
            )

            extension = "mp3"

            source_height = (
                info.get("height")
            )

            update_job(
                job_id,
                source_height=
                    source_height
            )

        # =================================================
        # VIDEO MODE
        # =================================================

        else:

            available = (
                get_available_heights(
                    info
                )
            )

            if not available:

                raise RuntimeError(
                    "No downloadable video "
                    "formats were found."
                )

            source_max = max(
                available
            )

            update_job(
                job_id,
                source_height=
                    source_max
            )

            # ---------------------------------------------
            # NO FAKE UPSCALING
            # ---------------------------------------------

            if quality > source_max:

                available_text = ", ".join(
                    f"{h}p"
                    for h in available
                )

                raise RuntimeError(

                    f"{quality}p is not available "
                    f"for this source. Maximum "
                    f"available quality is "
                    f"{source_max}p. Available: "
                    f"{available_text}. "
                    f"Please select another quality."
                )

            selected_video = (
                choose_source_format(
                    info,
                    quality
                )
            )

            if not selected_video:

                raise RuntimeError(
                    "A suitable video format "
                    "could not be selected."
                )

            video_format_id = (
                selected_video.get(
                    "format_id"
                )
            )

            if not video_format_id:

                raise RuntimeError(
                    "Video format ID is unavailable."
                )

            # Check whether an audio format exists.
            audio_format = (
                choose_audio_format(
                    info
                )
            )

            if audio_format:

                # Video-only + best audio.
                format_selector = (
                    f"{video_format_id}+bestaudio/"
                    f"{video_format_id}"
                )

            else:

                # Try the selected format itself.
                format_selector = (
                    str(video_format_id)
                )

            extension = "mp4"

            selected_height = int(
                selected_video.get(
                    "height"
                )
            )

            update_job(
                job_id,
                source_height=
                    selected_height
            )

        # =================================================
        # OUTPUT
        # =================================================

        output_template = str(

            job_dir /

            "%(title)s.%(ext)s"

        )

        options = extractor_options()

        options.update({

            "format":
                format_selector,

            "outtmpl":
                output_template,

            "progress_hooks":
                [
                    make_progress_hook(
                        job_id
                    )
                ],

            "merge_output_format":
                extension,

            "noplaylist":
                True,

            "restrictfilenames":
                False,

            "windowsfilenames":
                True,

        })

        # =================================================
        # MP3
        # =================================================

        if mode == "audio":

            options[
                "postprocessors"
            ] = [

                {
                    "key":
                        "FFmpegExtractAudio",

                    "preferredcodec":
                        "mp3",

                    "preferredquality":
                        "192"
                }

            ]

        # =================================================
        # DOWNLOAD
        # =================================================

        update_job(
            job_id,
            status="downloading"
        )

        if info.get("_avd_tiktok_fallback"):
            direct_formats = [f for f in info.get("formats", []) if f.get("url")]
            if not direct_formats:
                raise RuntimeError("TikTok returned no public video stream.")
            if mode == "video":
                target_candidates = [f for f in direct_formats if (f.get("height") or 0) >= quality]
                selected_direct = min(target_candidates, key=lambda f: f.get("height") or 10**9) if target_candidates else max(direct_formats, key=lambda f: f.get("height") or 0)
            else:
                selected_direct = direct_formats[0]
            direct_url = selected_direct["url"]
            direct_output = job_dir / "tiktok-direct.mp4"
            with curl_requests.get(
                direct_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0.0.0 Safari/537.36",
                    "Referer": "https://www.tiktok.com/",
                },
                impersonate="chrome",
                timeout=60,
                stream=True,
            ) as direct_response:
                direct_response.raise_for_status()
                total = int(direct_response.headers.get("content-length") or 0)
                downloaded = 0
                with direct_output.open("wb") as handle:
                    for chunk in direct_response.iter_content(chunk_size=1024 * 256):
                        if not chunk:
                            continue
                        handle.write(chunk)
                        downloaded += len(chunk)
                        update_job(
                            job_id,
                            status="downloading",
                            downloaded_bytes=downloaded,
                            total_bytes=total,
                            percentage=(downloaded / total * 100) if total else 0,
                            speed=0,
                        )
            output_file = direct_output
        else:
            with yt_dlp.YoutubeDL(
                options
            ) as ydl:
                downloaded_info = ydl.extract_info(
                    url,
                    download=True
                )


        # =================================================
        # FIND DOWNLOADED FILE
        # =================================================

        files = [

            f

            for f in job_dir.iterdir()

            if f.is_file()

            and not f.name.endswith(
                ".part"
            )

        ]

        if not files:

            raise RuntimeError(
                "No output file was produced."
            )

        output_file = max(

            files,

            key=lambda f:
                f.stat().st_size

        )

        # =================================================
        # AUDIO SAFETY CHECK
        # =================================================

        if mode == "video" and not has_audio_stream(output_file):
            update_job(job_id, status="processing", conversion=True)
            audio_template = str(job_dir / "fallback-audio.%(ext)s")
            audio_options = extractor_options()
            audio_options.update({
                "format": "bestaudio/best",
                "outtmpl": audio_template,
                "noplaylist": True,
            })
            with yt_dlp.YoutubeDL(audio_options) as audio_ydl:
                audio_ydl.extract_info(url, download=True)
            audio_files = [f for f in job_dir.iterdir() if f.is_file() and f.name.startswith("fallback-audio") and not f.name.endswith(".part")]
            if audio_files and ffmpeg_available():
                audio_file = max(audio_files, key=lambda f: f.stat().st_size)
                muxed = job_dir / "muxed-with-audio.mp4"
                mux_command = [
                    "ffmpeg", "-y", "-i", str(output_file), "-i", str(audio_file),
                    "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(muxed),
                ]
                mux = subprocess.run(mux_command, capture_output=True, text=True, encoding="utf-8", errors="replace")
                if mux.returncode == 0 and muxed.exists() and has_audio_stream(muxed):
                    output_file = muxed

        # =================================================
        # REAL LOWER-QUALITY CONVERSION
        # =================================================

        if mode == "video":

            selected_source_height = (
                get_job(job_id).get(
                    "source_height"
                )
                or 0
            )

            # If downloaded source is higher than
            # requested quality, genuinely resize it.
            if (
                selected_source_height
                and
                selected_source_height > quality
            ):

                converted_file = (
                    job_dir /
                    "converted.mp4"
                )

                resize_video(

                    output_file,

                    converted_file,

                    quality,

                    job_id

                )

                if not converted_file.exists():

                    raise RuntimeError(
                        "FFmpeg did not create "
                        "the converted file."
                    )

                output_file = (
                    converted_file
                )

        # =================================================
        # FINAL USER FILE
        # =================================================

        final_extension = (

            "mp3"

            if mode == "audio"

            else "mp4"

        )

        final_path = (
            unique_output_path(
                title,
                final_extension
            )
        )

        shutil.move(
            str(output_file),
            str(final_path)
        )

        actual_size = (
            final_path.stat().st_size
        )

        job = get_job(
            job_id
        )

        started_at = (
            job.get("started_at")
            or
            time.time()
        )

        elapsed = (
            time.time() -
            started_at
        )

        average_speed = (

            actual_size / elapsed

            if elapsed > 0

            else 0

        )

        # =================================================
        # COMPLETE
        # =================================================

        update_job(

            job_id,

            status="completed",

            percentage=100,

            downloaded_bytes=
                actual_size,

            total_bytes=
                actual_size,

            filesize=
                actual_size,

            filename=
                final_path.name,

            download_url=
                f"/api/file/{final_path.name}",

            elapsed=
                elapsed,

            speed=
                average_speed,

            eta=0,

            finished_at=
                time.time(),

            worker_running=False,

            paused=False,

            conversion=False

        )

        shutil.rmtree(
            job_dir,
            ignore_errors=True
        )

    except PauseDownload:

        update_job(

            job_id,

            status="paused",

            paused=True,

            worker_running=False

        )

    except Exception as error:

        error_text = str(
            error
        )

        print(
            f"[{job_id}] DOWNLOAD ERROR:",
            error_text
        )

        lower_error = (
            error_text.lower()
        )

        if (
            "cancelled by user"
            in lower_error
        ):

            message = (
                "Download cancelled."
            )

            status = "cancelled"

        elif (
            "not available for this source"
            in lower_error
        ):

            message = error_text
            status = "error"

        elif (
            "requested format is not available"
            in lower_error
        ):

            message = (
                f"{quality}p is not available "
                "for this source. Please select "
                "another quality."
            )

            status = "error"

        elif (
            "unsupported url"
            in lower_error
        ):

            message = (
                "This URL is not supported by "
                "the installed yt-dlp extractors."
            )

            status = "error"

        elif (
            "drm"
            in lower_error
        ):

            message = (
                "This media is DRM-protected."
            )

            status = "error"

        elif (
            "sign in"
            in lower_error
            or
            "login"
            in lower_error
        ):

            message = (
                "This source requires authentication."
            )

            status = "error"

        else:

            message = (
                "Download failed. The source may "
                "be unsupported, private, restricted, "
                "DRM-protected, or temporarily unavailable."
            )

            status = "error"

        update_job(

            job_id,

            status=status,

            error=message,

            worker_running=False,

            finished_at=
                time.time(),

            conversion=False

        )

    finally:

        final_job = get_job(
            job_id
        )

        if final_job:

            if final_job.get(
                "status"
            ) not in (
                "paused",
                "downloading",
                "converting"
            ):

                shutil.rmtree(
                    job_dir,
                    ignore_errors=True
                )


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# =========================================================
# INFO
# =========================================================

@app.post("/api/info")
def get_info():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    url = (
        data.get("url")
        or ""
    ).strip()

    if not url:

        return jsonify({
            "error":
                "Please paste a video URL."
        }), 400

    try:

        with yt_dlp.YoutubeDL(
            extractor_options()
        ) as ydl:

            info = extract_media_info(url)

        formats = []

        for fmt in info.get(
            "formats",
            []
        ):

            height = fmt.get(
                "height"
            )

            if not height:
                continue

            vcodec = fmt.get(
                "vcodec"
            )

            acodec = fmt.get(
                "acodec"
            )

            if (
                not vcodec
                or
                vcodec == "none"
            ):
                continue

            size = get_format_size(
                fmt
            )

            formats.append({

                "format_id":
                    fmt.get(
                        "format_id"
                    ),

                "height":
                    int(height),

                "width":
                    fmt.get(
                        "width"
                    ),

                "ext":
                    fmt.get(
                        "ext"
                    ),

                "fps":
                    fmt.get(
                        "fps"
                    ),

                "filesize":
                    size or None,

                "filesize_text":
                    format_bytes(
                        size
                    )
                    if size
                    else
                    "Size unavailable",

                "video_codec":
                    vcodec,

                "audio_codec":
                    acodec,

                "has_audio":
                    bool(
                        acodec
                        and
                        acodec != "none"
                    ),

                "tbr":
                    fmt.get(
                        "tbr"
                    ),

                "abr":
                    fmt.get(
                        "abr"
                    ),

            })

        available = (
            get_available_heights(
                info
            )
        )

        quality_data = []

        for height in available:

            selected = (
                choose_source_format(
                    info,
                    height
                )
            )

            size = (
                get_format_size(
                    selected
                )
                if selected
                else 0
            )

            quality_data.append({

                "height":
                    height,

                "filesize":
                    size or None,

                "filesize_text":
                    format_bytes(size)
                    if size
                    else
                    "Size unavailable"

            })

        return jsonify({

            "success":
                True,

            "title":
                info.get(
                    "title",
                    "Unknown video"
                ),

            "thumbnail":
                info.get(
                    "thumbnail"
                ),

            "duration":
                info.get(
                    "duration"
                ),

            "uploader":
                info.get(
                    "uploader"
                ),

            "extractor":
                info.get(
                    "extractor_key"
                ),

            "domain":
                get_domain(url),

            "webpage_url":
                info.get(
                    "webpage_url",
                    url
                ),

            "original_height":
                info.get(
                    "height"
                ),

            "available_qualities":
                available,

            "quality_data":
                quality_data,

            "formats":
                formats,

            "has_audio":
                any(
                    x.get(
                        "has_audio"
                    )
                    for x in formats
                ),

            "ffmpeg":
                ffmpeg_available()

        })

    except Exception as error:

        print(
            "INFO ERROR:",
            error
        )

        text = str(
            error
        )

        if "Unsupported URL" in text:

            message = (
                "This URL is not supported by "
                "the installed yt-dlp extractors."
            )

        elif "DRM" in text or "drm" in text.lower():

            message = (
                "This media is DRM-protected."
            )

        else:

            message = (
                "This URL could not be processed. "
                "The website may be unsupported, "
                "private, restricted, DRM-protected, "
                "or temporarily unavailable."
            )

        return jsonify({
            "error":
                message
        }), 400


# =========================================================
# START DOWNLOAD
# =========================================================

@app.post("/api/download")
def start_download():

    data = (
        request.get_json(
            silent=True
        )
        or {}
    )

    url = (
        data.get("url")
        or ""
    ).strip()

    mode = data.get(
        "mode",
        "video"
    )

    try:

        quality = int(
            data.get(
                "quality",
                720
            )
        )

    except Exception:

        quality = 720

    if not url:

        return jsonify({
            "error":
                "URL is required."
        }), 400

    if mode not in (
        "video",
        "audio"
    ):

        mode = "video"

    if quality < 1:

        quality = 720

    job_id = create_job(
        url,
        mode,
        quality
    )

    thread = threading.Thread(

        target=download_worker,

        args=(
            job_id,
            url,
            mode,
            quality
        ),

        daemon=True

    )

    thread.start()

    return jsonify({

        "success":
            True,

        "job_id":
            job_id,

        "status":
            "queued"

    })


# =========================================================
# STATUS
# =========================================================

@app.get("/api/download/<job_id>")
def download_status(job_id):

    job = get_job(
        job_id
    )

    if not job:

        return jsonify({
            "error":
                "Download job not found."
        }), 404

    job["downloaded_text"] = (
        format_bytes(
            job.get(
                "downloaded_bytes"
            )
        )
        if job.get(
            "downloaded_bytes"
        )
        else
        "0 B"
    )

    job["total_text"] = (
        format_bytes(
            job.get(
                "total_bytes"
            )
        )
        if job.get(
            "total_bytes"
        )
        else
        "Unknown"
    )

    job["filesize_text"] = (
        format_bytes(
            job.get(
                "filesize"
            )
        )
        if job.get(
            "filesize"
        )
        else
        "Unknown"
    )

    job["speed_text"] = (
        format_bytes(
            job.get(
                "speed"
            )
        )
        + "/s"
        if job.get(
            "speed"
        )
        else
        "0 B/s"
    )

    job["eta_text"] = (
        format_seconds(
            job.get(
                "eta"
            )
        )
        or
        "Calculating..."
    )

    job["elapsed_text"] = (
        format_seconds(
            job.get(
                "elapsed"
            )
        )
        or
        "0s"
    )

    return jsonify(
        job
    )


# =========================================================
# PAUSE
# =========================================================

@app.post("/api/download/<job_id>/pause")
def pause_download(job_id):

    job = get_job(
        job_id
    )

    if not job:

        return jsonify({
            "error":
                "Download job not found."
        }), 404

    if job.get(
        "status"
    ) not in (
        "downloading",
        "processing"
    ):

        return jsonify({
            "error":
                "This download is not currently running."
        }), 400

    update_job(
        job_id,
        paused=True
    )

    return jsonify({

        "success":
            True,

        "status":
            "pausing"

    })


# =========================================================
# RESUME
# =========================================================

@app.post("/api/download/<job_id>/resume")
def resume_download(job_id):

    job = get_job(
        job_id
    )

    if not job:

        return jsonify({
            "error":
                "Download job not found."
        }), 404

    if job.get(
        "status"
    ) != "paused":

        return jsonify({
            "error":
                "This download is not paused."
        }), 400

    update_job(

        job_id,

        paused=False,

        cancel_requested=False,

        status="queued"

    )

    thread = threading.Thread(

        target=download_worker,

        args=(
            job_id,
            job["url"],
            job["mode"],
            job["quality"]
        ),

        daemon=True

    )

    thread.start()

    return jsonify({

        "success":
            True,

        "status":
            "queued"

    })


# =========================================================
# CANCEL
# =========================================================

@app.post("/api/download/<job_id>/cancel")
def cancel_download(job_id):

    job = get_job(
        job_id
    )

    if not job:

        return jsonify({
            "error":
                "Download job not found."
        }), 404

    update_job(

        job_id,

        cancel_requested=True,

        status="cancelling"

    )

    return jsonify({

        "success":
            True,

        "status":
            "cancelling"

    })


# =========================================================
# FILE
# =========================================================

@app.get("/api/file/<path:filename>")
def download_file(filename):

    filename = Path(
        filename
    ).name

    file_path = (
        DOWNLOAD_DIR /
        filename
    )

    if not file_path.exists():

        return (
            "File not found",
            404
        )

    return send_file(

        file_path,

        as_attachment=True,

        download_name=
            file_path.name

    )


# =========================================================
# EXTRACTORS
# =========================================================

@app.get("/api/extractors")
def extractors():

    names = []

    for extractor in (
        yt_dlp.list_extractors()
    ):

        name = getattr(
            extractor,
            "IE_NAME",
            None
        )

        if name:

            names.append(
                name
            )

    names = sorted(
        set(names)
    )

    return jsonify({

        "count":
            len(names),

        "extractors":
            names

    })


# =========================================================
# HEALTH
# =========================================================

@app.get("/api/health")
def health():

    return jsonify({

        "status":
            "ok",

        "engine":
            "yt-dlp",

        "yt_dlp_version":
            getattr(
                yt_dlp.version,
                "__version__",
                "unknown"
            ),

        "extractor_count":
            len(
                list(
                    yt_dlp.list_extractors()
                )
            ),

        "ffmpeg":
            ffmpeg_available()

    })


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    app.run(

        host="127.0.0.1",

        port=5000,

        debug=True,

        threaded=True

    )