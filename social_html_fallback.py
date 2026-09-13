import html
import json
import re
from urllib.parse import urlparse

import media_features

try:
    from curl_cffi import requests as http_requests
except Exception:
    http_requests = None

_ORIGINAL_EXTRACT = media_features._extract_info


def _get_html(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        if http_requests is not None:
            response = http_requests.get(url, headers=headers, impersonate="chrome", timeout=30, allow_redirects=True)
            response.raise_for_status()
            return response.text, str(response.url), headers
        import urllib.request
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", "ignore"), response.geturl(), headers
    except Exception:
        return "", url, headers


def _clean(value):
    try:
        value = html.unescape(value)
        value = value.replace("\\/", "/").replace("\\u002F", "/")
        value = value.replace("\\u0026", "&")
        return value
    except Exception:
        return str(value)


def _urls(text):
    found = []
    seen = set()
    for raw in re.findall(r'https?:(?:\\/|/){2}[^"\'<>\\ ]+', text):
        url = _clean(raw).rstrip('\\"\'')
        if url not in seen:
            seen.add(url)
            found.append(url)
    return found


def _tiktok_photo(url):
    html_text, final_url, headers = _get_html(url)
    if not html_text:
        return None
    urls = []
    # TikTok image slideshow payloads commonly use imageURL/displayImage/urlList.
    for match in re.finditer(r'(?:imageURL|imageUrl|displayImage|urlList|url_list)[^\n]{0,1200}', html_text, re.I):
        for candidate in _urls(match.group(0)):
            lower = candidate.lower()
            if any(token in lower for token in (".jpg", ".jpeg", ".png", ".webp", "/obj/", "/tos-")):
                if candidate not in urls:
                    urls.append(candidate)
    if not urls:
        for candidate in _urls(html_text):
            lower = candidate.lower()
            if any(token in lower for token in (".jpg", ".jpeg", ".png", ".webp")) and candidate not in urls:
                urls.append(candidate)
    if not urls:
        return None
    return {
        "type": "images",
        "title": "TikTok Pictures",
        "source_url": final_url,
        "headers": headers,
        "_fallback_direct": True,
        "images": [{"url": x, "http_headers": headers} for x in urls[:40]],
    }


def _pinterest_html(url):
    html_text, final_url, headers = _get_html(url)
    if not html_text:
        return None
    def meta(name):
        pattern = rf'<meta[^>]+(?:property|name)=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)'
        match = re.search(pattern, html_text, re.I)
        if not match:
            pattern = rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(name)}["\']'
            match = re.search(pattern, html_text, re.I)
        return _clean(match.group(1)) if match else None
    image = meta("og:image") or meta("twitter:image")
    video = meta("og:video:secure_url") or meta("og:video")
    result = {"title": meta("og:title") or "Pinterest Media", "source_url": final_url, "headers": headers, "_fallback_direct": True}
    if image:
        result["images"] = [{"url": image, "http_headers": headers}]
    if video:
        result["type"] = "video"
        result["formats"] = [{"format_id": "pinterest-og", "url": video, "height": 0, "ext": "mp4", "vcodec": "h264", "acodec": "aac", "http_headers": headers}]
        return result
    if image:
        result["type"] = "images"
        return result
    return None


def _patched_extract(url):
    info = _ORIGINAL_EXTRACT(url)
    if isinstance(info, dict):
        if info.get("images") or info.get("formats") or info.get("type") == "images":
            return info
    host = urlparse(url).netloc.lower().removeprefix("www.")
    try:
        if host.endswith("tiktok.com") and re.search(r"/photo/", url, re.I):
            return _tiktok_photo(url) or info
        if host == "pin.it" or host.endswith("pinterest.com") or host.endswith("pinterest.co.uk") or host.endswith("pinterest.de") or host.endswith("pinterest.fr"):
            return _pinterest_html(url) or info
    except Exception:
        pass
    return info


media_features._extract_info = _patched_extract
