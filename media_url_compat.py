from urllib.parse import urlparse

import media_features


_original = media_features._allowed_special_url


def _allowed_special_url(url):
    try:
        host = urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:
        host = ""
    if host == "pin.it":
        return True
    return _original(url)


media_features._allowed_special_url = _allowed_special_url
