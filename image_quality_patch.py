"""Focused image extraction patch.

Keeps the existing downloader UI and video/audio paths untouched.  It fixes
image-post duplication, gives TikTok photo posts priority, and lets any
yt-dlp-supported public site expose explicit image media when available.
"""

import hashlib
import threading
from pathlib import Path
from urllib.parse import urlparse

import media_features
import site_fallbacks
from core_app import TEMP_DIR, jobs, jobs_lock, update_job


def _identity(url):
    try:
        parsed = urlparse(str(url).strip())
        if not parsed.netloc or not parsed.path:
            return str(url).strip().lower()
        return (parsed.netloc.lower(), parsed.path.rstrip("/").lower())
    except Exception:
        return str(url).strip().lower()


def _collect_explicit_images(value, output=None, seen=None):
    output = output if output is not None else []
    seen = seen if seen is not None else set()
    if isinstance(value, dict):
        # Only collect fields that represent actual post images.  Do not treat
        # thumbnails/covers as separate pictures.
        for key in ("images", "image_list", "imageList", "imageURLList", "imageUrls", "image_urls"):
            child = value.get(key)
            if isinstance(child, dict):
                child = list(child.values())
            if isinstance(child, list):
                for item in child:
                    url = None
                    width = height = None
                    headers = {}
                    if isinstance(item, str):
                        url = item
                    elif isinstance(item, dict):
                        width = item.get("width") or item.get("w")
                        height = item.get("height") or item.get("h")
                        headers = item.get("http_headers") or {}
                        for key2 in ("url", "imageURL", "imageUrl", "displayImage", "originImage", "url_orig", "url_original"):
                            raw = item.get(key2)
                            if isinstance(raw, str) and raw.startswith(("http://", "https://")):
                                url = raw
                                break
                            if isinstance(raw, dict):
                                url = raw.get("url")
                                if url:
                                    break
                            if isinstance(raw, list):
                                for candidate in raw:
                                    if isinstance(candidate, str) and candidate.startswith(("http://", "https://")):
                                        url = candidate
                                        break
                                    if isinstance(candidate, dict) and candidate.get("url"):
                                        url = candidate["url"]
                                        break
                                if url:
                                    break
                    if isinstance(url, str) and url.startswith(("http://", "https://")):
                        ident = _identity(url)
                        if ident not in seen:
                            seen.add(ident)
                            output.append({"url": url, "width": width, "height": height, "http_headers": headers})
        for child in value.values():
            _collect_explicit_images(child, output, seen)
    elif isinstance(value, list):
        for child in value:
            _collect_explicit_images(child, output, seen)
    return output


def _fallback_images(url):
    try:
        fallback = site_fallbacks.resolve(url)
    except Exception:
        fallback = None
    if not isinstance(fallback, dict):
        return []
    return _collect_explicit_images(fallback)


def _extract_candidates(url):
    # First use the normal yt-dlp extractor. This keeps image support broad:
    # every public site for which yt-dlp exposes explicit image media can work.
    try:
        info = media_features._extract_info(url)
    except Exception:
        info = None
    candidates = _collect_explicit_images(info)

    # TikTok gets a dedicated fallback because photo posts can be absent from
    # the ordinary webpage extraction. The existing public resolver already
    # handles the item-detail fallback, so use its exact image URLs here.
    if not candidates or "tiktok.com" in urlparse(url).netloc.lower():
        fallback = _fallback_images(url)
        if fallback:
            merged = []
            seen = set()
            for item in candidates + fallback:
                ident = _identity(item.get("url"))
                if ident in seen:
                    continue
                seen.add(ident)
                merged.append(item)
            candidates = merged

    # Stable ordering while removing duplicate URL variants.
    unique = []
    seen = set()
    for item in candidates:
        url_value = item.get("url")
        ident = _identity(url_value)
        if not url_value or ident in seen:
            continue
        seen.add(ident)
        unique.append(item)
    return unique[:40]


def _download_image_list_dedup(job_id, source_url, image_list):
    job_dir = TEMP_DIR / f"images_{job_id}"
    job_dir.mkdir(parents=True, exist_ok=True)
    import time
    started_at = time.time()
    update_job(job_id, status="starting", started_at=started_at, worker_running=True)
    saved = []
    digests = set()
    try:
        total = len(image_list)
        for index, item in enumerate(image_list, 1):
            image_url = str(item.get("url") or "").strip()
            if not image_url.startswith(("http://", "https://")):
                continue
            try:
                suffix = Path(urlparse(image_url).path).suffix.lower()
                if suffix not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
                    suffix = ".jpg"
                temp = job_dir / f"image_{len(saved) + 1:03d}{suffix}"
                media_features._download_image(image_url, source_url, temp, item.get("http_headers"))
                if not temp.exists() or temp.stat().st_size <= 0:
                    continue
                digest = hashlib.sha256(temp.read_bytes()).hexdigest()
                if digest in digests:
                    temp.unlink(missing_ok=True)
                    continue
                digests.add(digest)
                saved.append(temp)
            except Exception:
                continue
            update_job(job_id, status="downloading", percentage=(index / max(total, 1)) * 100,
                       downloaded_bytes=sum(p.stat().st_size for p in saved if p.exists()), total_bytes=0)

        if not saved:
            raise RuntimeError("No downloadable pictures were found for this post.")

        with jobs_lock:
            title = jobs.get(job_id, {}).get("title") or "Pictures"
        folder = media_features.unique_output_path(title, "jpg").with_suffix("")
        folder.mkdir(parents=True, exist_ok=True)
        final_paths = []
        for index, temp in enumerate(saved, 1):
            target = folder / f"{index:03d}{temp.suffix or '.jpg'}"
            temp.replace(target)
            final_paths.append(target)

        import zipfile
        zip_path = folder.with_suffix(".zip")
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in final_paths:
                archive.write(path, arcname=path.name)
        size = zip_path.stat().st_size
        elapsed = max(time.time() - started_at, 0.001)
        update_job(job_id, status="completed", percentage=100, downloaded_bytes=size,
                   total_bytes=size, filesize=size, filename=zip_path.name,
                   download_url=f"/api/special-file/{zip_path.name}", elapsed=elapsed,
                   speed=size / elapsed, eta=0, finished_at=time.time(), worker_running=False)
    except Exception as error:
        update_job(job_id, status="error", error=str(error), worker_running=False, finished_at=time.time())
    finally:
        import shutil
        shutil.rmtree(job_dir, ignore_errors=True)


def _image_worker(job_id, url):
    try:
        candidates = _extract_candidates(url)
        if not candidates:
            raise RuntimeError("No downloadable pictures were found for this post.")
        title = "Pictures"
        with jobs_lock:
            title = jobs.get(job_id, {}).get("title") or title
        update_job(job_id, title=title)
        _download_image_list_dedup(job_id, url, candidates)
    except Exception as error:
        update_job(job_id, status="error", error=str(error), worker_running=False, finished_at=__import__("time").time())


# Replace only the image worker; all existing video/audio/history/UI workers stay intact.
media_features._image_worker = _image_worker
