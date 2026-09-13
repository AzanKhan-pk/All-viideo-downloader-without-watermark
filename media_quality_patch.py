import shutil
import subprocess
import time
from pathlib import Path

from flask import jsonify, request

import core_app
import media_features
from core_app import app, TEMP_DIR, update_job, unique_output_path, ffmpeg_available


# Pinterest/TikTok sometimes expose only a higher real source format.
# The requested quality must still be the final output quality, so we
# download the nearest real source >= target and resize it with FFmpeg.
def _video_formats(info):
    result = []
    for fmt in info.get("formats") or []:
        if not isinstance(fmt, dict) or not fmt.get("url"):
            continue
        try:
            height = int(fmt.get("height") or 0)
        except Exception:
            height = 0
        vcodec = str(fmt.get("vcodec") or "none").lower()
        if height > 0 and vcodec != "none":
            result.append(fmt)
    return result


def _select_video(info, target):
    formats = _video_formats(info)
    if not formats:
        return None
    heights = sorted({int(f.get("height")) for f in formats if f.get("height")})
    if not heights:
        return None
    max_height = max(heights)
    if int(target) > max_height:
        return None
    suitable = [h for h in heights if h >= int(target)]
    chosen_height = min(suitable) if suitable else max_height
    candidates = [f for f in formats if int(f.get("height")) == chosen_height]
    candidates.sort(key=lambda f: (
        1 if f.get("acodec") and str(f.get("acodec")).lower() != "none" else 0,
        f.get("filesize") or f.get("filesize_approx") or 0,
        f.get("tbr") or 0,
        f.get("fps") or 0,
    ), reverse=True)
    return candidates[0]


def _audio_exists(info):
    for fmt in info.get("formats") or []:
        if not isinstance(fmt, dict):
            continue
        acodec = str(fmt.get("acodec") or "none").lower()
        if acodec != "none":
            return True
    return False


def _selector(info, selected):
    fmt_id = str(selected.get("format_id") or "")
    if not fmt_id:
        return None
    acodec = str(selected.get("acodec") or "none").lower()
    if acodec != "none":
        return fmt_id
    if _audio_exists(info):
        return f"{fmt_id}+bestaudio/{fmt_id}"
    return fmt_id


def _safe_move_or_copy(source, target):
    try:
        shutil.move(str(source), str(target))
    except Exception:
        shutil.copy2(str(source), str(target))


def _quality_resize(job_id, source, quality):
    converted = source.parent / "converted-final.mp4"
    core_app.resize_video(source, converted, int(quality), job_id)
    if not converted.exists() or converted.stat().st_size <= 0:
        raise RuntimeError("FFmpeg did not create the requested quality file.")
    return converted


def _finish(job_id, final_path, started_at):
    if not final_path.exists() or final_path.stat().st_size <= 0:
        raise RuntimeError("The final media file was not created correctly.")
    size = final_path.stat().st_size
    elapsed = max(time.time() - (started_at or time.time()), 0.001)
    update_job(job_id, status="completed", percentage=100, downloaded_bytes=size,
               total_bytes=size, filesize=size, filename=final_path.name,
               download_url=f"/api/file/{final_path.name}", elapsed=elapsed,
               speed=size / elapsed, eta=0, finished_at=time.time(),
               worker_running=False, conversion=False)


def _quality_worker(job_id, url, quality):
    job_dir = TEMP_DIR / f"special_{job_id}"
    job_dir.mkdir(parents=True, exist_ok=True)
    started_at = time.time()
    update_job(job_id, status="starting", started_at=started_at, worker_running=True,
               target_height=int(quality), conversion=False)
    try:
        info = media_features._extract_info(url)
        if not info:
            raise RuntimeError("The site did not return usable public media data.")
        title = info.get("title") or "video"
        selected = _select_video(info, quality)
        if selected:
            source_height = int(selected.get("height") or 0)
            selector = _selector(info, selected)
            if not selector:
                raise RuntimeError("No usable video format was returned by the site.")
            update_job(job_id, title=title, source_height=source_height, status="downloading")
            options = media_features._options(url)
            options.update({
                "format": selector,
                "outtmpl": str(job_dir / "%(title)s.%(ext)s"),
                "merge_output_format": "mp4",
                "progress_hooks": [core_app.make_progress_hook(job_id)],
                "noplaylist": True,
                "retries": 10,
                "fragment_retries": 10,
                "file_access_retries": 10,
            })
            with media_features.yt_dlp.YoutubeDL(options) as ydl:
                downloaded = ydl.extract_info(url, download=True)
            title = downloaded.get("title") or title
            files = [p for p in job_dir.iterdir() if p.is_file() and not p.name.endswith((".part", ".ytdl"))]
            if not files:
                raise RuntimeError("Download completed, but no final video file was produced.")
            mp4s = [p for p in files if p.suffix.lower() == ".mp4"]
            output = max(mp4s or files, key=lambda p: p.stat().st_size)
            if source_height > int(quality):
                output = _quality_resize(job_id, output, quality)
            final = unique_output_path(title, "mp4")
            _safe_move_or_copy(output, final)
            _finish(job_id, final, started_at)
            return

        fallback = media_features._fallback_info(url)
        if not fallback:
            raise RuntimeError(f"{int(quality)}p is not available for this source.")
        formats = fallback.get("formats") or []
        direct = [f for f in formats if isinstance(f, dict) and f.get("url")]
        if not direct:
            raise RuntimeError("No downloadable video stream was returned by the site.")
        heights = [int(f.get("height") or 0) for f in direct]
        max_height = max(heights or [0])
        if max_height and int(quality) > max_height:
            raise RuntimeError(f"{int(quality)}p is not available for this source. Maximum available quality is {max_height}p.")
        direct.sort(key=lambda f: int(f.get("height") or 0))
        candidates = [f for f in direct if int(f.get("height") or 0) >= int(quality)]
        selected = candidates[0] if candidates else direct[-1]
        source_height = int(selected.get("height") or 0)
        update_job(job_id, title=fallback.get("title") or title, source_height=source_height, status="downloading")
        source = job_dir / "source.mp4"
        media_features._download_direct(selected["url"], source, url, selected.get("http_headers") or fallback.get("headers"))
        if fallback.get("audio_url") and ffmpeg_available():
            audio = job_dir / "audio.m4a"
            media_features._download_direct(fallback["audio_url"], audio, url, fallback.get("headers"))
            merged = job_dir / "merged.mp4"
            command = ["ffmpeg", "-y", "-i", str(source), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-movflags", "+faststart", str(merged)]
            result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
            if result.returncode == 0 and merged.exists() and merged.stat().st_size > 0:
                source = merged
        if source_height > int(quality):
            source = _quality_resize(job_id, source, quality)
        final = unique_output_path(fallback.get("title") or title, "mp4")
        _safe_move_or_copy(source, final)
        _finish(job_id, final, started_at)
    except Exception as error:
        update_job(job_id, status="error", error=str(error), worker_running=False, finished_at=time.time(), conversion=False)
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


# Replace only the focused TikTok/Pinterest worker; the general downloader is untouched.
media_features._special_video_worker = _quality_worker


def _image_candidate_patch(info):
    candidates = list(media_features._image_candidates(info) or [])
    seen = {str(x.get("url")) for x in candidates if isinstance(x, dict) and x.get("url")}

    def add(url, item=None):
        url = str(url or "").strip()
        if not url.startswith(("http://", "https://")) or url in seen:
            return
        seen.add(url)
        item = item if isinstance(item, dict) else {}
        candidates.append({
            "url": url,
            "width": item.get("width") or item.get("w"),
            "height": item.get("height") or item.get("h"),
            "ext": item.get("ext"),
            "http_headers": item.get("http_headers") or info.get("headers") or {},
        })

    def walk(node, image_context=False):
        if isinstance(node, dict):
            keys = set(str(k).lower() for k in node.keys())
            context = image_context or any(any(token in k for token in ("image", "photo", "picture", "slideshow", "image_post", "url_list")) for k in keys)
            for key, value in node.items():
                key_l = str(key).lower()
                child_context = context or any(token in key_l for token in ("image", "photo", "picture", "slideshow", "image_post", "url_list"))
                if isinstance(value, str) and child_context and value.startswith(("http://", "https://")):
                    add(value, node)
                elif isinstance(value, list):
                    for entry in value:
                        if isinstance(entry, str) and child_context:
                            add(entry, node)
                        else:
                            walk(entry, child_context)
                elif isinstance(value, dict):
                    walk(value, child_context)
        elif isinstance(node, list):
            for value in node:
                walk(value, image_context)

    walk(info)
    candidates.sort(key=lambda x: ((x.get("width") or 0) * (x.get("height") or 0), x.get("width") or 0), reverse=True)
    return candidates[:40]


media_features._image_candidates = _image_candidate_patch


def _preview():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url or not media_features._allowed_special_url(url):
        return jsonify({"error": "Please use a public TikTok or Pinterest URL."}), 400
    info = media_features._extract_info(url)
    if not info:
        return jsonify({"error": "The site did not return usable public media data."}), 500
    fallback = media_features._fallback_info(url)
    if fallback and fallback.get("type") == "video" and not info.get("formats"):
        info = fallback
    images = media_features._image_candidates(info)
    if fallback:
        images = images or (fallback.get("images") or [])
    video_formats = _video_formats(info)
    title = (fallback or {}).get("title") or info.get("title") or "Public media"
    thumbnails = info.get("thumbnails") or []
    thumbnail = info.get("thumbnail") or info.get("thumbnail_url")
    if not thumbnail and thumbnails:
        thumbs = [x for x in thumbnails if isinstance(x, dict) and x.get("url")]
        if thumbs:
            thumbs.sort(key=lambda x: ((x.get("width") or 0) * (x.get("height") or 0)), reverse=True)
            thumbnail = thumbs[0].get("url")
    if not thumbnail and fallback:
        thumbnail = fallback.get("thumbnail")
    is_photo = bool(images) and not bool(video_formats)
    return jsonify({
        "success": True,
        "title": title,
        "extractor": info.get("extractor_key") or info.get("extractor"),
        "is_photo": is_photo,
        "thumbnail": thumbnail,
        "images": images,
    })


app.view_functions["media_preview"] = _preview
