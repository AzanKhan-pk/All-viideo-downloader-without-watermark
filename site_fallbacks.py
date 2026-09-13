import html as html_lib
import json
import re
from urllib.parse import urlparse

try:
    from curl_cffi import requests as http_requests
except Exception:
    http_requests = None


UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/140.0.0.0 Safari/537.36"
)


def _get(url, referer=None):
    headers = {
        "User-Agent": UA,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    if referer:
        headers["Referer"] = referer
    if http_requests is not None:
        response = http_requests.get(url, headers=headers, impersonate="chrome", timeout=25, allow_redirects=True)
        response.raise_for_status()
        return response.text, str(response.url), headers

    import urllib.request
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read().decode("utf-8", "ignore"), response.geturl(), headers


def _script_json(html, script_id):
    marker = f'id="{script_id}"'
    start = html.find(marker)
    if start < 0:
        marker = f"id='{script_id}'"
        start = html.find(marker)
    if start < 0:
        return None
    start = html.find(">", start)
    end = html.find("</script>", start)
    if start < 0 or end < 0:
        return None
    raw = html[start + 1:end].strip()
    try:
        return json.loads(html_lib.unescape(raw))
    except Exception:
        return None


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _urls(value):
    out = []
    seen = set()
    for item in _walk(value):
        for key in ("url", "urlList", "url_list", "url_list", "src", "srcSet"):
            raw = item.get(key) if isinstance(item, dict) else None
            values = raw if isinstance(raw, list) else [raw]
            for candidate in values:
                if not isinstance(candidate, str):
                    continue
                candidate = candidate.replace("\\u0026", "&")
                if candidate.startswith("http") and candidate not in seen:
                    seen.add(candidate)
                    out.append(candidate)
    return out


def _tiktok_item(data, video_id):
    if not isinstance(data, dict):
        return None
    scope = data.get("__DEFAULT_SCOPE__")
    if isinstance(scope, dict):
        detail = scope.get("webapp.video-detail")
        if isinstance(detail, dict):
            item = ((detail.get("itemInfo") or {}).get("itemStruct"))
            if isinstance(item, dict):
                return item
    module = data.get("ItemModule")
    if isinstance(module, dict):
        item = module.get(video_id)
        if isinstance(item, dict):
            return item
        for candidate in module.values():
            if isinstance(candidate, dict) and str(candidate.get("id")) == str(video_id):
                return candidate
    for item in _walk(data):
        if isinstance(item, dict):
            if str(item.get("id")) == str(video_id) and (item.get("video") or item.get("imagePost")):
                return item
    return None


def _direct_url(value):
    if isinstance(value, str) and value.startswith("http"):
        return value
    if isinstance(value, dict):
        for key in ("urlList", "url_list", "url"):
            raw = value.get(key)
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, str) and item.startswith("http"):
                        return item
            elif isinstance(raw, str) and raw.startswith("http"):
                return raw
    return None


def tiktok(url):
    match = re.search(r"/(?:video|photo)/(\d+)", url)
    if not match:
        return None
    video_id = match.group(1)
    html, final_url, headers = _get(url, "https://www.tiktok.com/")
    data = _script_json(html, "__UNIVERSAL_DATA_FOR_REHYDRATION__")
    item = _tiktok_item(data, video_id) if data else None
    if item is None:
        data = _script_json(html, "SIGI_STATE")
        item = _tiktok_item(data, video_id) if data else None
    if not item:
        return None

    image_urls = []
    image_post = item.get("imagePost") or {}
    for image in image_post.get("images") or []:
        if not isinstance(image, dict):
            continue
        value = image.get("imageURL") or image.get("imageUrl") or image
        candidate = _direct_url(value)
        if candidate and candidate not in image_urls:
            image_urls.append(candidate)

    video = item.get("video") or {}
    video_url = _direct_url(video.get("playAddr")) or _direct_url(video.get("downloadAddr"))
    music = item.get("music") or {}
    audio_url = _direct_url(music.get("playUrl"))

    title = item.get("desc") or item.get("shareTitle") or f"TikTok {video_id}"
    result = {"title": title, "source_url": final_url, "headers": headers}
    if image_urls:
        result["type"] = "images"
        result["images"] = [{"url": x, "width": None, "height": None, "http_headers": headers} for x in image_urls]
        if audio_url:
            result["audio_url"] = audio_url
        return result
    if video_url:
        result["type"] = "video"
        result["formats"] = [{"format_id": "tiktok-direct", "url": video_url, "height": (video.get("height") or 0), "ext": "mp4", "vcodec": "h264", "acodec": "aac", "http_headers": headers}]
        if audio_url:
            result["audio_url"] = audio_url
        return result
    return None


def _pin_record(data, pin_id):
    if not isinstance(data, dict):
        return None
    for node in _walk(data):
        pins = node.get("pins") if isinstance(node, dict) else None
        if isinstance(pins, dict):
            pin = pins.get(pin_id)
            if isinstance(pin, dict):
                return pin
    for node in _walk(data):
        if isinstance(node, dict) and str(node.get("id")) == str(pin_id):
            return node
    return None


def _pin_images(pin):
    candidates = []
    seen = set()
    def add(url, width=None, height=None):
        if isinstance(url, str) and url.startswith("http") and url not in seen:
            seen.add(url)
            candidates.append({"url": url, "width": width, "height": height})
    image = pin.get("images") if isinstance(pin, dict) else None
    if isinstance(image, dict):
        for value in image.values():
            if isinstance(value, dict):
                add(value.get("url"), value.get("width"), value.get("height"))
    media = pin.get("media") if isinstance(pin, dict) else None
    if isinstance(media, dict):
        image = media.get("images") or media.get("image")
        if isinstance(image, dict):
            for value in image.values():
                if isinstance(value, dict):
                    add(value.get("url"), value.get("width"), value.get("height"))
    for node in _walk(pin):
        if not isinstance(node, dict):
            continue
        for key in ("url_orig", "url_original", "originals"):
            value = node.get(key)
            if isinstance(value, str):
                add(value, node.get("width"), node.get("height"))
    return candidates


def _pin_videos(pin):
    videos = []
    seen = set()
    for node in _walk(pin):
        if not isinstance(node, dict):
            continue
        for key in ("url", "src"):
            value = node.get(key)
            if not isinstance(value, str) or not value.startswith("http") or value in seen:
                continue
            context = " ".join(str(node.get(k, "")) for k in ("type", "mime_type", "format", "width", "height")).lower()
            if ".mp4" in value.lower() or "video" in context:
                seen.add(value)
                videos.append({"url": value, "width": node.get("width"), "height": node.get("height")})
    return videos


def pinterest(url):
    match = re.search(r"/pin/(\d+)", url)
    if not match:
        # pin.it is resolved by the HTTP request first.
        match = re.search(r"(\d{12,})", url)
    html, final_url, headers = _get(url, "https://www.pinterest.com/")
    if not match:
        match = re.search(r"/pin/(\d+)", final_url)
    if not match:
        return None
    pin_id = match.group(1)
    data = _script_json(html, "__PWS_DATA__")
    if data is None:
        data = _script_json(html, "__PWS_INITIAL_PROPS__")
    pin = _pin_record(data, pin_id) if data else None
    if not pin:
        # Open Graph is a useful final fallback for single-image Pins.
        og_image = re.search(r'<meta[^>]+property=[\"\']og:image[\"\'][^>]+content=[\"\']([^\"\']+)', html, re.I)
        if og_image:
            return {"type": "images", "title": f"Pinterest {pin_id}", "source_url": final_url, "headers": headers, "images": [{"url": html_lib.unescape(og_image.group(1)), "width": None, "height": None, "http_headers": headers}]}
        return None
    images = _pin_images(pin)
    videos = _pin_videos(pin)
    title = pin.get("title") or pin.get("grid_title") or pin.get("description") or f"Pinterest {pin_id}"
    result = {"title": title, "source_url": final_url, "headers": headers}
    if videos:
        result["type"] = "video"
        result["formats"] = [{"format_id": f"pin-direct-{i}", "url": v["url"], "height": v.get("height") or 0, "ext": "mp4", "vcodec": "h264", "acodec": "aac", "http_headers": headers} for i, v in enumerate(videos)]
        if images:
            result["images"] = images
        return result
    if images:
        result["type"] = "images"
        result["images"] = [dict(x, http_headers=headers) for x in images]
        return result
    return None


def resolve(url):
    host = urlparse(url).netloc.lower().removeprefix("www.")
    if host == "tiktok.com" or host.endswith(".tiktok.com"):
        return tiktok(url)
    if host == "pinterest.com" or host.endswith(".pinterest.com") or host == "pin.it":
        return pinterest(url)
    return None
