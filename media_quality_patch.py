import shutil
import subprocess
import time
from pathlib import Path

from flask import jsonify, request

import core_app
import media_features
from core_app import app, TEMP_DIR, update_job, unique_output_path, ffmpeg_available

# Keep the original extractor helper. The previous patch called the replacement
# recursively, which caused a Flask 500 HTML response (<!DOCTYPE ...>) instead of JSON.
_ORIGINAL_IMAGE_CANDIDATES = media_features._image_candidates


def _video_formats(info):
    result = []
    for fmt in info.get("formats") or []:
        if not isinstance(fmt, dict) or not fmt.get("url"):
            continue
        try:
            height = int(fmt.get("height") or 0)
        except Exception:
            height = 0
        if height > 0 and str(fmt.get("vcodec") or "none").lower() != "none":
            result.append(fmt)
    return result


def _select_video(info, target):
    formats = _video_formats(info)
    if not formats:
        return None
    heights = sorted({int(f.get("height")) for f in formats if f.get("height")})
    if not heights or int(target) > max(heights):
        return None
    chosen_height = min(h for h in heights if h >= int(target))
    candidates = [f for f in formats if int(f.get("height") or 0) == chosen_height]
    candidates.sort(key=lambda f: (
        1 if str(f.get("acodec") or "none") != "none" else 0,
        f.get("tbr") or 0,
        f.get("fps") or 0,
        f.get("filesize") or f.get("filesize_approx") or 0,
    ), reverse=True)
    return candidates[0]


def _audio_exists(info):
    return any(str(f.get("acodec") or "none") != "none" for f in info.get("formats") or [] if isinstance(f, dict))


def _resize_video(source, destination, quality):
    command = [
        "ffmpeg", "-y", "-i", str(source),
        "-vf", f"scale=-2:{int(quality)}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
        "-c:a", "aac", "-movflags", "+faststart", str(destination),
    ]
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0 or not destination.exists() or destination.stat().st_size <= 0:
        raise RuntimeError("FFmpeg could not create the requested quality file.")
    return destination


def _quality_worker(job_id, url, quality):
    job_dir = TEMP_DIR / f"special_{job_id}"
    job_dir.mkdir(parents=True, exist_ok=True)
    started_at = time.time()
    update_job(job_id, status="starting", started_at=started_at, worker_running=True,
               target_height=int(quality), conversion=False)
    try:
        info = media_features._extract_info(url)
        if not info:
            raise RuntimeError("The site did not return usable media data.")
        title = info.get("title") or "video"
        selected = _select_video(info, quality)
        fallback = media_features._fallback_info(url) or info

        # For fallback/direct streams, select a real source and optionally merge audio.
        if selected is None:
            direct = [f for f in (fallback.get("formats") or [])
                      if isinstance(f, dict) and f.get("url")]
            if not direct:
                raise RuntimeError(f"{int(quality)}p is not available for this source.")
            direct_heights = [int(f.get("height") or 0) for f in direct]
            max_height = max(direct_heights or [0])
            if max_height and int(quality) > max_height:
                raise RuntimeError(f"{int(quality)}p is not available. Maximum available quality is {max_height}p.")
            direct.sort(key=lambda f: int(f.get("height") or 0))
            higher = [f for f in direct if int(f.get("height") or 0) >= int(quality)]
            selected = higher[0] if higher else direct[-1]
            info = fallback

        source_height = int(selected.get("height") or 0)
        update_job(job_id, title=info.get("title") or title,
                   source_height=source_height, status="downloading")

        job_output = job_dir / "source.mp4"
        format_id = str(selected.get("format_id") or "")
        if format_id and not info.get("_fallback_direct"):
            selector = format_id
            if str(selected.get("acodec") or "none") == "none" and _audio_exists(info):
                selector = f"{format_id}+bestaudio/{format_id}"
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
            source = max(mp4s or files, key=lambda p: p.stat().st_size)
        else:
            source = job_output
            media_features._download_direct(selected["url"], source, url,
                                             selected.get("http_headers") or info.get("headers"))
            audio_url = info.get("audio_url")
            if audio_url and ffmpeg_available():
                audio = job_dir / "audio.m4a"
                try:
                    media_features._download_direct(audio_url, audio, url, info.get("headers"))
                    merged = job_dir / "merged.mp4"
                    command = ["ffmpeg", "-y", "-i", str(source), "-i", str(audio),
                               "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                               "-c:a", "aac", "-movflags", "+faststart", str(merged)]
                    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            text=True, encoding="utf-8", errors="replace")
                    if result.returncode == 0 and merged.exists() and merged.stat().st_size > 0:
                        source = merged
                except Exception:
                    pass

        # The final file is really converted to the selected resolution.
        if source_height > int(quality):
            if not ffmpeg_available():
                raise RuntimeError("FFmpeg is required to create a lower requested quality.")
            source = _resize_video(source, job_dir / "requested-quality.mp4", quality)

        final = unique_output_path(title, "mp4")
        shutil.move(str(source), str(final))
        size = final.stat().st_size
        elapsed = max(time.time() - started_at, 0.001)
        update_job(job_id, status="completed", percentage=100, downloaded_bytes=size,
                   total_bytes=size, filesize=size, filename=final.name,
                   download_url=f"/api/file/{final.name}", elapsed=elapsed,
                   speed=size / elapsed, eta=0, finished_at=time.time(),
                   worker_running=False, conversion=False)
    except Exception as error:
        update_job(job_id, status="error", error=str(error), worker_running=False,
                   finished_at=time.time(), conversion=False)
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


media_features._special_video_worker = _quality_worker


def _image_candidates(info):
    candidates = list(_ORIGINAL_IMAGE_CANDIDATES(info) or [])
    seen = {str(x.get("url")) for x in candidates if isinstance(x, dict) and x.get("url")}

    def add(url, node=None):
        url = str(url or "").strip()
        if not url.startswith(("http://", "https://")) or url in seen:
            return
        seen.add(url)
        node = node if isinstance(node, dict) else {}
        candidates.append({
            "url": url,
            "width": node.get("width") or node.get("w"),
            "height": node.get("height") or node.get("h"),
            "ext": node.get("ext"),
            "http_headers": node.get("http_headers") or info.get("headers") or {},
        })

    def walk(node, image_context=False):
        if isinstance(node, dict):
            keys = [str(k).lower() for k in node.keys()]
            context = image_context or any(any(t in k for t in ("image", "photo", "picture", "slideshow", "imagepost", "url_list", "urllist")) for k in keys)
            for key, value in node.items():
                key_l = str(key).lower()
                child_context = context or any(t in key_l for t in ("image", "photo", "picture", "slideshow", "imagepost", "url_list", "urllist"))
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


media_features._image_candidates = _image_candidates


def _preview():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url or not media_features._allowed_special_url(url):
        return jsonify({"error": "Please use a public TikTok or Pinterest URL."}), 400
    info = media_features._extract_info(url)
    if not info:
        return jsonify({"error": "The site did not return usable public media data."}), 500
    fallback = media_features._fallback_info(url)
    images = _image_candidates(info)
    if fallback:
        images = images or (fallback.get("images") or [])
    type_info = fallback if fallback and not info.get("formats") else info
    video_formats = _video_formats(type_info)
    thumbnail = info.get("thumbnail") or info.get("thumbnail_url")
    if not thumbnail and images:
        thumbnail = images[0].get("url")
    if not thumbnail and fallback:
        thumbnail = fallback.get("thumbnail")
    title = (fallback or {}).get("title") or info.get("title") or "Public media"
    return jsonify({
        "success": True,
        "title": title,
        "extractor": info.get("extractor_key") or info.get("extractor"),
        "is_photo": bool(images) and not bool(video_formats),
        "thumbnail": thumbnail,
        "images": images,
    })


app.view_functions["media_preview"] = _preview
