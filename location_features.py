import os
import subprocess
import sys
from pathlib import Path

from flask import jsonify

import core_app


BASE_DIR = Path(__file__).resolve().parent
LOCATION_FILE = BASE_DIR / "download_location.txt"


def _load_saved_location():
    try:
        if not LOCATION_FILE.exists():
            return
        saved = LOCATION_FILE.read_text(encoding="utf-8").strip()
        if not saved:
            return
        path = Path(saved).expanduser().resolve()
        path.mkdir(parents=True, exist_ok=True)
        core_app.DOWNLOAD_DIR = path
    except Exception:
        # Never prevent the downloader from starting because of a saved path.
        pass


def _save_location(path):
    try:
        LOCATION_FILE.write_text(str(path), encoding="utf-8")
    except Exception:
        # Location still works for the current session if persistence fails.
        pass


def _open_folder(path):
    path = Path(path).resolve()
    path.mkdir(parents=True, exist_ok=True)

    if sys.platform.startswith("win"):
        os.startfile(str(path), "explore")
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


_load_saved_location()


@core_app.app.get("/api/location")
def get_location():
    path = Path(core_app.DOWNLOAD_DIR).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return jsonify({"success": True, "path": str(path)})


@core_app.app.post("/api/location/open")
def open_location():
    try:
        path = Path(core_app.DOWNLOAD_DIR).resolve()
        _open_folder(path)
        return jsonify({"success": True, "path": str(path)})
    except Exception as error:
        return jsonify({"error": f"Could not open download folder: {error}"}), 500


@core_app.app.post("/api/location/browse")
def browse_location():
    if not sys.platform.startswith("win"):
        return jsonify({"error": "Folder selection is available in the Windows desktop app."}), 400

    try:
        import tkinter as tk
        from tkinter import filedialog

        current = Path(core_app.DOWNLOAD_DIR).resolve()
        current.mkdir(parents=True, exist_ok=True)

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(
            initialdir=str(current),
            title="Choose Download Location",
        )
        root.destroy()

        if not selected:
            return jsonify({
                "success": True,
                "cancelled": True,
                "path": str(current),
            })

        selected_path = Path(selected).resolve()
        selected_path.mkdir(parents=True, exist_ok=True)
        core_app.DOWNLOAD_DIR = selected_path
        _save_location(selected_path)
        _open_folder(selected_path)

        return jsonify({
            "success": True,
            "path": str(selected_path),
        })
    except Exception as error:
        return jsonify({"error": f"Could not choose download location: {error}"}), 500
