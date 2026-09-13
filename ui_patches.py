from flask import request

import core_app
from core_app import app


@app.after_request
def inject_persistent_download_ui(response):
    try:
        if request.path == "/" and response.content_type and response.content_type.startswith("text/html"):
            body = response.get_data(as_text=True)
            marker = '<script src="/static/persistent_download_ui.js"></script>'
            if marker not in body and "</body>" in body:
                body = body.replace("</body>", marker + "</body>", 1)
                response.set_data(body)
    except Exception:
        pass
    return response
