from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
LAUNCHER = ROOT / "windows" / "launcher.py"


def add_once(text, marker, block, label):
    if block.strip() in text:
        return text
    if marker not in text:
        raise SystemExit(f"Patch target not found: {label}")
    return text.replace(marker, block + "\n" + marker, 1)


app = APP.read_text(encoding="utf-8")
if "# AVD PERSISTENCE + IMAGE GALLERY" not in app:
    app = app.replace(
        "import subprocess\nfrom pathlib import Path\nfrom urllib.parse import urlparse\n",
        "import subprocess\nimport json\nimport mimetypes\nimport urllib.request\nfrom pathlib import Path\nfrom urllib.parse import urlparse\n",
        1,
    )
    state_block = r'''# AVD PERSISTENCE + IMAGE GALLERY
STATE_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "All Video Downloader Without Watermark"
STATE_FILE = STATE_DIR / "jobs.json"
STATE_DIR.mkdir(parents=True, exist_ok=True)
_state_lock = threading.Lock()
_state_last_write = 0.0


def persist_jobs(force=False):
    global _state_last_write
    now = time.time()
    if not force and (now - _state_last_write) < 0.75:
        return
    try:
        with _state_lock:
            with jobs_lock:
                payload = {"version": 2, "jobs": [dict(job) for job in jobs.values()]}
            tmp = STATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            tmp.replace(STATE_FILE)
            _state_last_write = now
    except Exception as exc:
        print("JOB STATE SAVE ERROR:", exc)


def load_persisted_jobs():
    if not STATE_FILE.exists():
        return
    try:
        payload = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        saved = payload.get("jobs", []) if isinstance(payload, dict) else []
        with jobs_lock:
            for saved_job in saved:
                if not isinstance(saved_job, dict) or not saved_job.get("id"):
                    continue
                job = dict(saved_job)
                status = job.get("status")
                if status in {"starting", "downloading", "processing", "converting", "queued"}:
                    job["status"] = "queued"
                    job["worker_running"] = False
                    job["paused"] = False
                    job["cancel_requested"] = False
                jobs[job["id"]] = job
    except Exception as exc:
        print("JOB STATE LOAD ERROR:", exc)


def _image_extension(url, content_type=""):
    ext = Path(urlparse(url).path).suffix.lower().lstrip(".")
    if ext in {"jpg", "jpeg", "png", "webp", "gif", "bmp", "avif"}:
        return "jpg" if ext == "jpeg" else ext
    guessed = mimetypes.guess_extension((content_type or "").split(";", 1)[0].strip()) or ".jpg"
    return guessed.lstrip(".") or "jpg"


def _image_candidates(info):
    candidates, seen = [], set()
    def add(url, title="Image", width=None, height=None, source="yt-dlp"):
        if not isinstance(url, str) or not url.startswith(("http://", "https://")) or url in seen:
            return
        seen.add(url)
        candidates.append({"id": f"img-{len(candidates)+1}", "url": url, "title": title or "Image", "width": width, "height": height, "source": source})
    def walk(item):
        if not isinstance(item, dict):
            return
        title = item.get("title") or info.get("title") or "Image"
        for thumb in item.get("thumbnails") or []:
            if isinstance(thumb, dict):
                add(thumb.get("url"), title, thumb.get("width"), thumb.get("height"))
        for fmt in item.get("formats") or []:
            if not isinstance(fmt, dict):
                continue
            ext, vcodec = str(fmt.get("ext") or "").lower(), fmt.get("vcodec")
            if ext in {"jpg", "jpeg", "png", "webp", "gif", "bmp", "avif"} or (vcodec == "none" and ext in {"jpg", "jpeg", "png", "webp", "gif"}):
                add(fmt.get("url"), title, fmt.get("width"), fmt.get("height"))
        for entry in item.get("entries") or []:
            walk(entry)
    walk(info)
    return candidates


def _fallback_page_image(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36"})
        with urllib.request.urlopen(req, timeout=15) as response:
            content_type = response.headers.get("Content-Type", "")
            if content_type.lower().startswith("image/"):
                return [{"id": "img-1", "url": url, "title": "Image", "width": None, "height": None, "source": "direct"}]
            html = response.read(2_000_000).decode("utf-8", "ignore")
        found = []
        patterns = [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
        ]
        for pattern in patterns:
            for match in re.findall(pattern, html, flags=re.I):
                absolute = urllib.parse.urljoin(url, match)
                if absolute not in {x["url"] for x in found}:
                    found.append({"id": f"img-{len(found)+1}", "url": absolute, "title": "Page image", "width": None, "height": None, "source": "page"})
        return found[:30]
    except Exception:
        return []


def resume_persisted_jobs():
    load_persisted_jobs()
    to_resume = []
    with jobs_lock:
        for job in jobs.values():
            if job.get("status") == "queued" and job.get("url") and job.get("mode") in {"video", "audio"}:
                to_resume.append(job)
    for job in to_resume:
        threading.Thread(target=download_worker, args=(job["id"], job["url"], job.get("mode", "video"), int(job.get("quality") or 720)), daemon=True).start()
    persist_jobs(force=True)

'''
    app = add_once(app, "jobs = {}\njobs_lock = threading.Lock()", state_block, "job state marker")
    old_update = '''def update_job(job_id, **values):

    with jobs_lock:

        if job_id in jobs:
            jobs[job_id].update(values)
'''
    new_update = '''def update_job(job_id, **values):

    with jobs_lock:

        if job_id in jobs:
            jobs[job_id].update(values)

    if values.get("status") in {"completed", "error", "cancelled", "paused"}:
        persist_jobs(force=True)
    else:
        persist_jobs()
'''
    if old_update in app:
        app = app.replace(old_update, new_update, 1)
    image_routes = r'''
# =========================================================
# PUBLIC IMAGE GALLERY
# =========================================================

@app.post("/api/images")
def image_gallery():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "Image URL is required."}), 400
    try:
        options = extractor_options(url)
        options["noplaylist"] = False
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
        items = _image_candidates(info) or _fallback_page_image(url)
        return jsonify({"success": True, "title": info.get("title") or "Public images", "count": len(items), "images": items[:60]})
    except Exception as error:
        print("IMAGE INFO ERROR:", error)
        return jsonify({"error": "No public images could be extracted from this URL."}), 400


@app.post("/api/images/download")
def image_download():
    data = request.get_json(silent=True) or {}
    items = data.get("items") or []
    if not isinstance(items, list) or not items:
        return jsonify({"error": "Select at least one image."}), 400
    items = [x for x in items if isinstance(x, dict) and str(x.get("url", "")).startswith(("http://", "https://"))][:60]
    if not items:
        return jsonify({"error": "No valid image URLs were selected."}), 400
    job_id = uuid.uuid4().hex
    stamp = time.strftime("%Y%m%d_%H%M%S")
    folder_name = safe_filename(f"Images_{stamp}_{job_id[:6]}")
    target_dir = DOWNLOAD_DIR / folder_name
    target_dir.mkdir(parents=True, exist_ok=True)
    job = {"id": job_id, "url": data.get("source_url") or "", "domain": get_domain(data.get("source_url") or ""), "mode": "images", "quality": 0, "status": "queued", "title": f"Selected images ({len(items)})", "filename": folder_name, "download_url": None, "percentage": 0, "downloaded_bytes": 0, "total_bytes": 0, "filesize": None, "speed": 0, "eta": None, "elapsed": 0, "error": None, "paused": False, "cancel_requested": False, "started_at": time.time(), "finished_at": None, "worker_running": False, "source_height": None, "target_height": None, "conversion": False, "image_total": len(items), "image_done": 0, "image_folder": folder_name}
    with jobs_lock:
        jobs[job_id] = job
    persist_jobs(force=True)

    def worker():
        started = time.time()
        try:
            update_job(job_id, status="downloading", worker_running=True, started_at=started)
            total_bytes = 0
            for index, item in enumerate(items, start=1):
                current = get_job(job_id)
                if current and current.get("cancel_requested"):
                    raise RuntimeError("Download cancelled by user.")
                image_url = item["url"]
                req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36", "Referer": data.get("source_url") or image_url})
                filename = safe_filename(item.get("title") or f"image_{index}")
                path = target_dir / f"{index:03d}_{filename}.{_image_extension(image_url)}"
                with urllib.request.urlopen(req, timeout=30) as response:
                    content_type = response.headers.get("Content-Type", "")
                    if content_type and not content_type.lower().startswith("image/"):
                        raise RuntimeError("Selected URL is not an image.")
                    with path.open("wb") as out:
                        while True:
                            chunk = response.read(1024 * 128)
                            if not chunk:
                                break
                            out.write(chunk)
                            total_bytes += len(chunk)
                            update_job(job_id, downloaded_bytes=total_bytes, total_bytes=total_bytes, filesize=total_bytes, percentage=((index - 1) + 0.5) / len(items) * 100)
                update_job(job_id, image_done=index, percentage=index / len(items) * 100, downloaded_bytes=total_bytes, total_bytes=total_bytes, filesize=total_bytes)
            elapsed = max(time.time() - started, 0.001)
            update_job(job_id, status="completed", percentage=100, image_done=len(items), worker_running=False, finished_at=time.time(), elapsed=elapsed, speed=total_bytes / elapsed, eta=0, downloaded_bytes=total_bytes, total_bytes=total_bytes, filesize=total_bytes, filename=folder_name)
        except Exception as error:
            update_job(job_id, status="cancelled" if "cancelled" in str(error).lower() else "error", error=str(error), worker_running=False, finished_at=time.time())

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"success": True, "job_id": job_id, "folder": folder_name})


@app.get("/api/jobs")
def list_jobs():
    with jobs_lock:
        result = [dict(job) for job in jobs.values()]
    result.sort(key=lambda x: x.get("started_at") or 0, reverse=True)
    return jsonify({"success": True, "jobs": result[:100]})

'''
    app = add_once(app, "# =========================================================\n# EXTRACTORS", image_routes, "extractor route marker")
    app = app.replace('if __name__ == "__main__":\n\n    app.run(', 'if __name__ == "__main__":\n\n    resume_persisted_jobs()\n\n    app.run(', 1)
    APP.write_text(app, encoding="utf-8")


launcher = LAUNCHER.read_text(encoding="utf-8")
if "# AVD POLISHED BACKGROUND + GALLERY" not in launcher:
    launcher = launcher.replace(
        "import tempfile\nimport tkinter as tk\n",
        "import tempfile\nimport tkinter as tk\n\n# AVD POLISHED BACKGROUND + GALLERY\ntry:\n    from PIL import Image, ImageDraw\n    import pystray\nexcept Exception:\n    Image = None\n    ImageDraw = None\n    pystray = None\n",
        1,
    )
    method_block = '''    def open_download_file(self, filename):
        try:
            name = Path(str(filename or "")).name
            folder = Path(self.get_download_folder())
            target = folder / name
            if target.exists():
                subprocess.Popen(["explorer", "/select," + str(target)])
                return str(target)
            os.startfile(str(folder))
            return str(folder)
        except Exception as exc:
            return {"error": str(exc)}

'''
    launcher = add_once(launcher, "    def read_clipboard(self):", method_block, "WindowsBridge file opener")
    new_ui = r'''INJECTED_UI = r"""
(() => {
  const install = () => {
    if (document.getElementById('avd-enhanced-ui')) return;
    const style = document.createElement('style'); style.id='avd-enhanced-style';
    style.textContent=`#avd-native-tools{display:flex;width:100%;gap:8px;margin:10px 0 0;align-items:stretch}#avd-native-tools button{flex:1;min-height:42px;border:1px solid rgba(124,58,237,.45);border-radius:10px;padding:0 12px;cursor:pointer;font-weight:800;background:#17122b;color:#fff}#avd-native-tools button:hover{border-color:#facc15}.avd-job-close{position:absolute!important;top:8px!important;right:8px!important;width:30px!important;height:30px!important;padding:0!important;border:1px solid rgba(255,255,255,.12)!important;border-radius:9px!important;background:rgba(239,68,68,.12)!important;color:#ffb8b8!important;font:900 22px/28px Arial!important;cursor:pointer!important;z-index:8!important}.job{position:relative!important}.avd-file-btn{margin-left:8px;min-height:36px;padding:0 11px;border:1px solid rgba(124,58,237,.35);border-radius:9px;background:rgba(124,58,237,.12);color:#d8caff;cursor:pointer;font-weight:800}#avd-image-panel{margin-top:16px;padding:15px;border:1px solid rgba(124,58,237,.22);border-radius:17px;background:#0b0b12;display:none}#avd-image-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(135px,1fr));gap:10px}.avd-image-card{position:relative;border:1px solid rgba(255,255,255,.08);border-radius:12px;overflow:hidden;background:#11111a;cursor:pointer}.avd-image-card img{display:block;width:100%;aspect-ratio:1/1;object-fit:cover}.avd-image-card input{position:absolute;top:8px;right:8px;width:22px;height:22px;accent-color:#7c3aed;z-index:2}.avd-image-card.selected{border-color:#7c3aed;box-shadow:0 0 0 2px rgba(124,58,237,.24)}#avd-image-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}#avd-image-progress{height:8px;margin-top:12px;border-radius:999px;overflow:hidden;background:#252531;display:none}#avd-image-progress-bar{height:100%;width:0%;background:linear-gradient(90deg,#7c3aed,#a855f7,#facc15);transition:width .2s ease}@media(max-width:700px){#avd-native-tools{flex-direction:column}#avd-image-grid{grid-template-columns:repeat(2,1fr)}}`;
    document.head.appendChild(style);
    const input=document.querySelector('.inputrow input'); const qualities=document.querySelector('.qualities');
    if(qualities&&!document.getElementById('avd-native-tools')){const tools=document.createElement('div');tools.id='avd-native-tools';tools.innerHTML='<button type="button" id="avd-browse">📁 Browse location</button><button type="button" id="avd-open">📂 Open folder</button>';qualities.insertAdjacentElement('afterend',tools)}
    const panel=document.createElement('section');panel.id='avd-image-panel';panel.innerHTML='<div style="display:flex;justify-content:space-between;gap:10px;margin-bottom:12px"><strong>🖼 Public images</strong><span id="avd-image-count">0 selected</span></div><div id="avd-image-grid"></div><div id="avd-image-actions"><button type="button" class="small-btn" id="avd-image-select-all">Select all</button><button type="button" class="small-btn primary" id="avd-image-download">Download selected</button></div><div id="avd-image-progress"><div id="avd-image-progress-bar"></div></div>';
    const box=document.querySelector('.box'); if(box) box.appendChild(panel);
    const imageMode=document.createElement('button');imageMode.type='button';imageMode.id='avd-image-mode';imageMode.className='chip';imageMode.textContent='🖼 Images';imageMode.title='Load public images';document.querySelector('.modes')?.appendChild(imageMode);
    const api=window.pywebview&&window.pywebview.api;
    document.getElementById('avd-browse')?.addEventListener('click',()=>api?.browse_folder?.());document.getElementById('avd-open')?.addEventListener('click',()=>api?.open_download_folder?.());
    const hiddenJobs=new Set(JSON.parse(localStorage.getItem('avd-hidden-jobs')||'[]'));
    const hideJob=job=>{const key=job.dataset.avdJobId||job.querySelector('.job-title')?.textContent||'';hiddenJobs.add(key);localStorage.setItem('avd-hidden-jobs',JSON.stringify([...hiddenJobs].slice(-300)));job.remove()};
    const addClose=job=>{if(!job||job.querySelector('.avd-job-close'))return;const key=job.dataset.avdJobId||job.querySelector('.job-title')?.textContent||'';if(hiddenJobs.has(key)){job.style.display='none';return}const x=document.createElement('button');x.type='button';x.className='avd-job-close';x.textContent='×';x.title='Remove from list (keeps saved file)';x.onclick=e=>{e.preventDefault();e.stopPropagation();hideJob(job)};job.appendChild(x);const link=job.querySelector('.completed-link');if(link&&!job.querySelector('.avd-file-btn')){const name=decodeURIComponent((link.getAttribute('href')||'').split('/').pop()||'');const b=document.createElement('button');b.type='button';b.className='avd-file-btn';b.textContent='📂';b.title='Show file in folder';b.onclick=()=>api?.open_download_file?.(name);link.insertAdjacentElement('afterend',b)}};
    new MutationObserver(()=>document.querySelectorAll('.job').forEach(addClose)).observe(document.body,{childList:true,subtree:true});setTimeout(()=>document.querySelectorAll('.job').forEach(addClose),300);
    const renderJob=j=>{if(!j?.id||hiddenJobs.has(j.id))return;let c=document.querySelector(`.job[data-avd-job-id="${CSS.escape(j.id)}"]`);if(!c){const list=document.querySelector('.jobs');if(!list)return;c=document.createElement('article');c.className='job';c.dataset.avdJobId=j.id;c.innerHTML='<div class="job-top"><div class="job-title"></div><div class="job-status"></div></div><div class="job-progress"><div class="job-bar"></div></div><div class="job-stats"><div class="stat"><div class="stat-label">Progress</div><div class="stat-value p"></div></div><div class="stat"><div class="stat-label">File size</div><div class="stat-value s"></div></div><div class="stat"><div class="stat-label">Speed</div><div class="stat-value sp"></div></div><div class="stat"><div class="stat-label">Time remaining</div><div class="stat-value e"></div></div></div><div class="job-actions"></div>';list.prepend(c)}c.querySelector('.job-title').textContent=j.title||j.filename||'Download';c.querySelector('.job-status').textContent=String(j.status||'queued').toUpperCase();c.querySelector('.job-bar').style.width=Math.max(0,Math.min(100,Number(j.percentage||0)))+'%';c.querySelector('.p').textContent=Math.round(Number(j.percentage||0))+'%';c.querySelector('.s').textContent=j.filesize_text||j.total_text||'Unknown';c.querySelector('.sp').textContent=j.speed_text||'0 B/s';c.querySelector('.e').textContent=j.eta_text||(j.status==='completed'?'Complete':'Calculating...');const a=c.querySelector('.job-actions');a.innerHTML='';if(j.status==='completed'&&j.filename){if(j.mode==='images'){const f=document.createElement('button');f.className='completed-link';f.type='button';f.textContent='📂 Open image folder';f.onclick=()=>api?.open_download_folder?.();a.appendChild(f)}else{const l=document.createElement('a');l.className='completed-link';l.href='/api/file/'+encodeURIComponent(j.filename);l.download=j.filename;l.textContent='↓ Save '+j.filename;a.appendChild(l);const b=document.createElement('button');b.className='avd-file-btn';b.type='button';b.textContent='📂';b.title='Show file in folder';b.onclick=()=>api?.open_download_file?.(j.filename);a.appendChild(b)}}addClose(c)};
    const sync=async()=>{try{const r=await fetch('/api/jobs');const d=await r.json();(d.jobs||[]).forEach(renderJob)}catch(e){}};sync();setInterval(sync,1000);
    const grid=document.getElementById('avd-image-grid'),count=document.getElementById('avd-image-count');let items=[],imageJobId=null;const selectUpdate=()=>{const n=grid.querySelectorAll('input:checked').length;count.textContent=n+' selected';grid.querySelectorAll('.avd-image-card').forEach(c=>c.classList.toggle('selected',!!c.querySelector('input:checked')))};
    imageMode.onclick=async()=>{const url=(input?.value||'').trim();if(!url){alert('Paste a public media/image URL first.');return}panel.style.display='block';grid.innerHTML='<div style="padding:10px;color:#999">Loading images…</div>';try{const r=await fetch('/api/images',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});const d=await r.json();if(!r.ok)throw Error(d.error||'Could not load images');items=d.images||[];grid.innerHTML='';items.forEach((it,i)=>{const card=document.createElement('label');card.className='avd-image-card';card.innerHTML=`<input type="checkbox" data-index="${i}"><img loading="lazy" src="${it.url}" alt="">`;grid.appendChild(card)});selectUpdate();if(!items.length)grid.innerHTML='<div style="padding:10px;color:#999">No public images were found.</div>'}catch(e){grid.innerHTML='<div style="padding:10px;color:#ffb8b8">'+String(e.message||e)+'</div>'}};grid.onchange=selectUpdate;document.getElementById('avd-image-select-all').onclick=()=>{grid.querySelectorAll('input').forEach(x=>x.checked=true);selectUpdate()};document.getElementById('avd-image-download').onclick=async()=>{const selected=[...grid.querySelectorAll('input:checked')].map(x=>items[Number(x.dataset.index)]).filter(Boolean);if(!selected.length){alert('Select at least one image.');return}try{const r=await fetch('/api/images/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source_url:(input?.value||'').trim(),items:selected})});const d=await r.json();if(!r.ok)throw Error(d.error||'Image download failed');imageJobId=d.job_id;document.getElementById('avd-image-progress').style.display='block';const poll=async()=>{if(!imageJobId)return;try{const rr=await fetch('/api/download/'+imageJobId);const j=await rr.json();document.getElementById('avd-image-progress-bar').style.width=Math.max(0,Math.min(100,Number(j.percentage||0)))+'%';if(!['completed','error','cancelled'].includes(j.status))setTimeout(poll,700);else imageJobId=null}catch(e){setTimeout(poll,1200)}};poll()}catch(e){alert(String(e.message||e))}};
  };if(document.readyState==='loading')window.addEventListener('DOMContentLoaded',()=>setTimeout(install,250),{once:true});else setTimeout(install,250)
})();
"""
'''
    launcher = re.sub(r'INJECTED_UI = r"""[\s\S]*?"""\n\ndef main', new_ui + "\n\ndef main", launcher, count=1)
    main_replacement = r'''def _make_tray_image():
    if Image is None or ImageDraw is None:
        return None
    image = Image.new("RGBA", (64, 64), (28, 16, 55, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((3, 3, 61, 61), radius=14, fill=(109, 40, 217, 255))
    draw.rectangle((29, 15, 35, 42), fill=(250, 204, 21, 255))
    draw.polygon([(20, 36), (32, 48), (44, 36)], fill=(250, 204, 21, 255))
    draw.line((18, 52, 46, 52), fill=(255, 255, 255, 255), width=4)
    return image


def main():
    check_for_update()
    data_root = prepare_runtime()
    bridge = WindowsBridge(data_root)
    server = threading.Thread(target=start_server, args=(data_root,), daemon=True)
    server.start()
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/health", timeout=1) as response:
                if response.status == 200:
                    break
        except Exception:
            time.sleep(0.25)
    window = webview.create_window(APP_NAME, f"http://127.0.0.1:{PORT}", width=1200, height=820, min_size=(900,650), text_select=True, js_api=bridge)
    state = {"allow_exit": False}
    tray_icon = None
    def on_closing():
        if state["allow_exit"]:
            return True
        try:
            window.hide()
            if tray_icon is not None:
                tray_icon.title = "All Video Downloader — downloading in background"
        except Exception:
            pass
        return False
    def show_window(icon=None, item=None):
        try:
            window.show(); window.restore()
        except Exception:
            pass
    def exit_app(icon=None, item=None):
        state["allow_exit"] = True
        try:
            if icon is not None: icon.stop()
        except Exception:
            pass
        try:
            window.destroy()
        except Exception:
            pass
    def start_tray():
        nonlocal tray_icon
        if pystray is None or Image is None:
            return
        try:
            tray_icon = pystray.Icon("All Video Downloader", _make_tray_image(), "All Video Downloader", menu=pystray.Menu(pystray.MenuItem("Open Downloader", show_window, default=True), pystray.MenuItem("Exit", exit_app)))
            tray_icon.run()
        except Exception as exc:
            print("TRAY ERROR:", exc)
    def inject_native_ui(window_obj):
        try:
            window_obj.evaluate_js(INJECTED_UI)
        except Exception:
            pass
    window.events.closing += on_closing
    window.events.loaded += inject_native_ui
    threading.Thread(target=start_tray, daemon=True).start()
    webview.start()
'''
    launcher = re.sub(r'def main\(\):[\s\S]*?\n\nif __name__ == "__main__":\n    main\(\)', main_replacement + '\n\nif __name__ == "__main__":\n    main()', launcher, count=1)
    launcher = launcher.replace(
        '    downloader_app.DOWNLOAD_DIR = default_download_dir\n    downloader_app.app.run(',
        '    downloader_app.DOWNLOAD_DIR = default_download_dir\n    if hasattr(downloader_app, "resume_persisted_jobs"):\n        downloader_app.resume_persisted_jobs()\n    downloader_app.app.run(',
        1,
    )
    LAUNCHER.write_text(launcher, encoding="utf-8")

print("Persistent downloads, background tray mode, folder controls, removable cards, and public image gallery patched.")
