"""Final completed-download UI placement fix."""
from flask import request
from core_app import app

@app.after_request
def _final_completed_ui(response):
    try:
        if request.path == "/" and response.content_type and response.content_type.startswith("text/html"):
            body = response.get_data(as_text=True)
            marker = "final-ui-reliability-v2"
            if marker not in body and "</body>" in body:
                patch = '''<style id="final-ui-reliability-v2">
.completed-link{margin-right:0!important}
.avd-history-actions{margin-left:auto!important;justify-content:flex-end!important;align-items:center!important}
[data-field="complete"]{display:flex!important;align-items:center!important;justify-content:space-between!important;gap:12px!important;width:100%!important}
.avd-open-folder{white-space:nowrap!important;min-width:auto!important;padding:7px 12px!important}
</style>
<script>(function(){function fix(){document.querySelectorAll('.job [data-field="complete"]').forEach(function(box){box.style.display='flex';box.style.alignItems='center';box.style.justifyContent='space-between';box.style.width='100%';var a=box.querySelector('.avd-history-actions');if(a){a.style.marginLeft='auto';a.style.justifyContent='flex-end';var b=a.querySelector('.avd-open-folder');if(b){b.textContent='📂 Open in folder';b.title='Open in folder';b.setAttribute('aria-label','Open in folder');}}});}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fix);else fix();new MutationObserver(fix).observe(document.documentElement,{childList:true,subtree:true});setInterval(fix,1000);})();</script>'''
                body = body.replace("</body>", patch + "</body>", 1)
                response.set_data(body)
    except Exception:
        pass
    return response
