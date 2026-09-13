import json
import os
import subprocess
import threading
import time
import uuid
from pathlib import Path

from flask import jsonify, request

import core_app
from core_app import app

_HISTORY_FILE = Path(core_app.DOWNLOAD_DIR).parent / "download_history.json"
_HISTORY_LOCK = threading.Lock()


def _load_history():
    try:
        if not _HISTORY_FILE.exists():
            return []
        with _HISTORY_FILE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save_history(items):
    temp = _HISTORY_FILE.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(items[:200], handle, ensure_ascii=False, indent=2)
    os.replace(temp, _HISTORY_FILE)


def _safe_file(relative):
    base = Path(core_app.DOWNLOAD_DIR).resolve()
    value = str(relative or "").strip().replace("\\", "/")
    target = (base / value).resolve()
    if target != base and base not in target.parents:
        return None
    return target


def _record_completed_job(job):
    if not isinstance(job, dict) or str(job.get("status", "")).lower() != "completed":
        return
    filename = str(job.get("filename") or "").strip()
    if not filename:
        return
    target = _safe_file(filename)
    if not target or not target.is_file() or target.stat().st_size <= 0:
        return
    item = {
        "id": uuid.uuid4().hex,
        "title": str(job.get("title") or filename),
        "filename": filename,
        "relative_path": filename.replace("\\", "/"),
        "download_url": str(job.get("download_url") or f"/api/file/{filename}"),
        "mode": str(job.get("mode") or "video"),
        "created_at": int(job.get("finished_at") or time.time()),
        "filesize": target.stat().st_size,
    }
    with _HISTORY_LOCK:
        items = _load_history()
        items = [old for old in items if old.get("relative_path") != item["relative_path"]]
        items.insert(0, item)
        _save_history(items)


_original_core_update_job = core_app.update_job


def _history_update_job(job_id, **values):
    _original_core_update_job(job_id, **values)
    if str(values.get("status", "")).lower() == "completed":
        try:
            _record_completed_job(core_app.get_job(job_id))
        except Exception:
            pass


core_app.update_job = _history_update_job

# These modules imported update_job directly, so patch their local bindings too.
try:
    import media_features
    media_features.update_job = _history_update_job
except Exception:
    pass
try:
    import media_quality_patch
    media_quality_patch.update_job = _history_update_job
except Exception:
    pass


@app.get("/api/history")
def get_history():
    with _HISTORY_LOCK:
        items = _load_history()
    valid = []
    for item in items:
        if not isinstance(item, dict):
            continue
        target = _safe_file(item.get("relative_path") or item.get("filename"))
        if target and target.is_file() and target.stat().st_size > 0:
            item["filesize"] = target.stat().st_size
            valid.append(item)
    if len(valid) != len(items):
        with _HISTORY_LOCK:
            _save_history(valid)
    return jsonify({"success": True, "items": valid})


@app.post("/api/history")
def add_history():
    data = request.get_json(silent=True) or {}
    filename = str(data.get("filename") or "").strip()
    relative = str(data.get("relative_path") or filename).strip().replace("\\", "/")
    target = _safe_file(relative)
    if not filename or not target or not target.is_file():
        return jsonify({"error": "Completed file was not found."}), 400
    item = {
        "id": uuid.uuid4().hex,
        "title": str(data.get("title") or filename),
        "filename": filename,
        "relative_path": relative,
        "download_url": str(data.get("download_url") or f"/api/file/{filename}"),
        "mode": str(data.get("mode") or "video"),
        "created_at": int(data.get("created_at") or time.time()),
        "filesize": target.stat().st_size,
    }
    with _HISTORY_LOCK:
        items = _load_history()
        items = [old for old in items if old.get("relative_path") != relative]
        items.insert(0, item)
        _save_history(items)
    return jsonify({"success": True, "item": item})


@app.delete("/api/history/<history_id>")
def remove_history(history_id):
    with _HISTORY_LOCK:
        items = _load_history()
        kept = [item for item in items if str(item.get("id")) != str(history_id)]
        _save_history(kept)
    return jsonify({"success": True})


@app.post("/api/history/open")
def open_history_file():
    data = request.get_json(silent=True) or {}
    target = _safe_file(data.get("relative_path") or data.get("filename"))
    if not target or not target.exists():
        return jsonify({"error": "Downloaded file was not found."}), 404
    try:
        if os.name == "nt":
            subprocess.Popen(["explorer.exe", "/select,", str(target)])
        elif hasattr(os, "startfile"):
            os.startfile(str(target))
        else:
            subprocess.Popen(["xdg-open", str(target.parent)])
    except Exception as error:
        return jsonify({"error": f"Unable to open the file location: {error}"}), 500
    return jsonify({"success": True, "path": str(target)})
