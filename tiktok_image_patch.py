from urllib.parse import urlparse

import media_features


_ORIGINAL = media_features._image_candidates


def _looks_like_image(entry):
    if not isinstance(entry, dict):
        return False
    ext = str(entry.get("ext") or "").lower().lstrip(".")
    mime = str(entry.get("mime_type") or entry.get("mime") or "").lower()
    url = str(entry.get("url") or "").lower()
    vcodec = str(entry.get("vcodec") or "").lower()
    acodec = str(entry.get("acodec") or "").lower()
    if ext in {"jpg", "jpeg", "png", "webp", "avif", "gif", "heic"} or mime.startswith("image/"):
        return True
    if vcodec == "none" and acodec == "none" and ("image" in url or url.endswith((".jpg", ".jpeg", ".png", ".webp"))):
        return True
    return False


def _patched(info):
    candidates = list(_ORIGINAL(info) or [])
    seen = {str(item.get("url")) for item in candidates if isinstance(item, dict) and item.get("url")}

    def walk(node):
        if isinstance(node, dict):
            yield node
            for value in node.values():
                yield from walk(value)
        elif isinstance(node, list):
            for value in node:
                yield from walk(value)

    for entry in walk(info):
        if not _looks_like_image(entry):
            continue
        url = str(entry.get("url") or "").strip()
        if not url.startswith(("http://", "https://")) or url in seen:
            continue
        seen.add(url)
        candidates.append({
            "url": url,
            "width": entry.get("width") or entry.get("w"),
            "height": entry.get("height") or entry.get("h"),
            "ext": entry.get("ext"),
            "http_headers": entry.get("http_headers") or info.get("headers") or {},
        })

    candidates.sort(key=lambda x: ((x.get("width") or 0) * (x.get("height") or 0), x.get("width") or 0), reverse=True)
    return candidates[:40]


media_features._image_candidates = _patched
