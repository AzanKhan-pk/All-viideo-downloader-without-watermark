from flask import request
from core_app import app

@app.after_request
def inject_persistent_download_ui(response):
    try:
        if request.path == "/" and response.content_type and response.content_type.startswith("text/html"):
            body = response.get_data(as_text=True)
            markers = (
                '<script src="/static/input_repair.js"></script>',
                '<script src="/static/mouse_click_recovery.js"></script>',
                '<script src="/static/persistent_download_ui.js"></script>',
                '<script src="/static/special_preview_ui.js"></script>',
                '<script src="/static/text_selection_patch.js"></script>',
                '<script src="/static/progress_size_stability_patch.js"></script>',
                '<script src="/static/folder_action_position_patch.js"></script>',
                '<script src="/static/final_ui_reliability_patch.js"></script>'
            )
            if "</body>" in body:
                for marker in markers:
                    if marker not in body:
                        body = body.replace("</body>", marker + "</body>", 1)
                response.set_data(body)
    except Exception:
        pass
    return response
