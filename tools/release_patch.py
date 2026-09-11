from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path, old, new, label):
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Patch target not found: {label}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1) Use yt-dlp's format resolver for the requested quality instead of locking
#    downloads to one format id. This is more reliable when a site exposes
#    separate video/audio streams and fixes false "select another quality"
#    failures. If the exact requested height is unavailable, the best source
#    below it is used rather than failing the whole download.
app = ROOT / "app.py"
replace_once(
    app,
    '''            if quality > source_max:\n\n                available_text = ", ".join(\n                    f"{h}p"\n                    for h in available\n                )\n\n                raise RuntimeError(\n\n                    f"{quality}p is not available "\n                    f"for this source. Maximum "\n                    f"available quality is "\n                    f"{source_max}p. Available: "\n                    f"{available_text}. "\n                    f"Please select another quality."\n                )\n\n            selected_video = (\n                choose_source_format(\n                    info,\n                    quality\n                )\n            )\n\n            if not selected_video:\n\n                raise RuntimeError(\n                    "A suitable video format "\n                    "could not be selected."\n                )\n\n            video_format_id = (\n                selected_video.get(\n                    "format_id"\n                )\n            )\n\n            if not video_format_id:\n\n                raise RuntimeError(\n                    "Video format ID is unavailable."\n                )\n\n            # Check whether an audio format exists.\n            audio_format = (\n                choose_audio_format(\n                    info\n                )\n            )\n\n            if audio_format:\n\n                # Video-only + best audio.\n                format_selector = (\n                    f"{video_format_id}+bestaudio/"\n                    f"{video_format_id}"\n                )\n\n            else:\n\n                # Try the selected format itself.\n                format_selector = (\n                    str(video_format_id)\n                )\n\n            extension = "mp4"\n\n            selected_height = int(\n                selected_video.get(\n                    "height"\n                )\n            )\n''',
    '''            # Never reject a request just because the exact height is not\n            # present. yt-dlp will use the best source at or below the request;\n            # if no lower source exists it falls back to the best available\n            # source, which is then resized by FFmpeg when needed.\n            effective_quality = min(quality, source_max)\n\n            format_selector = (\n                f"bestvideo[height<={effective_quality}]+bestaudio/"\n                f"best[height<={effective_quality}]/"\n                "bestvideo+bestaudio/best"\n            )\n\n            extension = "mp4"\n\n            selected_video = choose_source_format(\n                info,\n                effective_quality\n            )\n            selected_height = int(\n                selected_video.get("height")\n            ) if selected_video else source_max\n''',
    "quality selector",
)

# 2) The final file size is already calculated from the actual completed file.
#    Keep progress estimates separate so the UI never treats an estimate as a
#    final size. The completed response remains authoritative.
replace_once(
    app,
    '''                filesize=\n                    total or job.get(\n                        "filesize"\n                    )\n''',
    '''                # This is a transfer estimate only. The final filesize is\n                # overwritten from final_path.stat().st_size after processing.\n                filesize=\n                    job.get("filesize")\n''',
    "progress filesize estimate",
)

# 3) Allow the UI to request a public image URL/page and resolve common
#    OpenGraph/Twitter image metadata. This is intentionally limited to public
#    HTTP(S) media and does not bypass private/restricted content.
marker = '''# =========================================================\n# START DOWNLOAD\n# =========================================================\n'''
image_route = r'''# =========================================================
# PUBLIC IMAGE DOWNLOAD
# =========================================================

@app.post("/api/image")
def download_public_image():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return jsonify({"error": "Please provide a public HTTP(S) image or page URL."}), 400

    import html as _html
    import urllib.request as _urlreq
    from urllib.parse import urljoin as _urljoin

    try:
        request_obj = _urlreq.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36"},
        )
        with _urlreq.urlopen(request_obj, timeout=25) as response:
            raw = response.read(12 * 1024 * 1024)
            content_type = (response.headers.get("Content-Type") or "").lower()
            final_url = response.geturl()

        image_url = final_url if content_type.startswith("image/") else None
        if not image_url:
            page = raw.decode("utf-8", errors="ignore")
            import re as _re
            for pattern in (
                r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
                r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
            ):
                match = _re.search(pattern, page, _re.I)
                if match:
                    image_url = _html.unescape(_urljoin(final_url, match.group(1)))
                    break

        if not image_url:
            return jsonify({"error": "No public image was found at this URL."}), 400

        image_request = _urlreq.Request(
            image_url,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with _urlreq.urlopen(image_request, timeout=25) as response:
            image_data = response.read(20 * 1024 * 1024)
            image_type = (response.headers.get("Content-Type") or "").lower()
            final_image_url = response.geturl()

        if not image_type.startswith("image/"):
            return jsonify({"error": "The resolved URL is not a public image."}), 400

        ext = image_type.split("/", 1)[1].split(";", 1)[0].lower()
        ext = {"jpeg": "jpg", "svg+xml": "svg", "webp": "webp", "png": "png", "gif": "gif"}.get(ext, "jpg")
        name = safe_filename(Path(urlparse(final_image_url).path).stem or "image")
        output = unique_output_path(name, ext)
        output.write_bytes(image_data)
        return jsonify({
            "success": True,
            "filename": output.name,
            "filesize": output.stat().st_size,
            "filesize_text": format_bytes(output.stat().st_size),
            "download_url": f"/api/file/{output.name}",
        })
    except Exception as error:
        print("IMAGE ERROR:", error)
        return jsonify({"error": "The public image could not be downloaded."}), 400


'''
replace_once(app, marker, image_route + marker, "public image route")

# 4) Permit the new image action through the API without changing video/audio behavior.
replace_once(
    app,
    '''    if mode not in (\n        "video",\n        "audio"\n    ):\n\n        mode = "video"\n''',
    '''    if mode not in (\n        "video",\n        "audio",\n        "image"\n    ):\n\n        mode = "video"\n\n    if mode == "image":\n        return jsonify({\n            "error": "Use the image download action for public images."\n        }), 400\n''',
    "mode validation",
)

# 5) Add an Image button to the existing web UI. It uses the dedicated public
#    image endpoint and leaves the existing video/audio controls untouched.
html = ROOT / "templates" / "index.html"
replace_once(
    html,
    '''        <button class="chip" data-mode="audio" type="button">🎵 Audio · MP3</button>\n''',
    '''        <button class="chip" data-mode="audio" type="button">🎵 Audio · MP3</button>\n        <button class="chip" id="imageModeButton" type="button">🖼 Image</button>\n''',
    "image mode button",
)
replace_once(
    html,
    '''let currentMode = "video";\nlet currentQuality = 144;\n''',
    '''let currentMode = "video";\nlet currentQuality = 144;\nlet imageMode = false;\n''',
    "image mode state",
)
replace_once(
    html,
    '''document.querySelectorAll("[data-mode]").forEach(button => { button.addEventListener("click", () => { document.querySelectorAll("[data-mode]").forEach(item => item.classList.remove("active")); button.classList.add("active"); currentMode = button.dataset.mode; if (lastInfo) renderResult(lastInfo); }); });\n''',
    '''document.querySelectorAll("[data-mode]").forEach(button => { button.addEventListener("click", () => { document.querySelectorAll("[data-mode]").forEach(item => item.classList.remove("active")); button.classList.add("active"); currentMode = button.dataset.mode; imageMode = false; if (lastInfo) renderResult(lastInfo); }); });\nconst imageModeButton = $("#imageModeButton");\nimageModeButton.addEventListener("click", () => { document.querySelectorAll("[data-mode]").forEach(item => item.classList.remove("active")); imageMode = !imageMode; imageModeButton.classList.toggle("active", imageMode); currentMode = "image"; $("#status").textContent = imageMode ? "Image mode — paste a public image or page URL." : "Ready — paste a public media URL."; });\n''',
    "image mode handler",
)
replace_once(
    html,
    '''async function startDownload() { const url = $("#url").value.trim(); if (!url) { showToast("Please paste a URL first."); return; } const button = $("#downloadBtn"); button.disabled = true; button.textContent = "Creating download…"; try { const response = await fetch("/api/download", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: url, mode: currentMode, quality: currentQuality }) }); const data = await response.json(); if (!response.ok) throw new Error(data.error || "Download could not be started."); if (!data.job_id) throw new Error("Server did not return a download job ID."); createJobCard(data.job_id); $("#status").textContent = "Download started. You can paste another URL."; showToast("Download started."); $("#url").focus(); $("#url").select(); } catch (error) { $("#status").textContent = error.message; showToast(error.message); } finally { button.disabled = false; button.textContent = currentMode === "audio" ? "🎵 Start MP3 Download" : `⬇ Start ${currentQuality}p MP4 Download`; } }\n''',
    '''async function startDownload() { const url = $("#url").value.trim(); if (!url) { showToast("Please paste a URL first."); return; } const button = $("#downloadBtn"); button.disabled = true; button.textContent = imageMode ? "Downloading image…" : "Creating download…"; try { if (imageMode) { const response = await fetch("/api/image", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url }) }); const data = await response.json(); if (!response.ok) throw new Error(data.error || "Image could not be downloaded."); const link = document.createElement("a"); link.href = data.download_url; link.download = data.filename || "image"; link.click(); $("#status").textContent = `Image downloaded — ${data.filesize_text || "size verified"}.`; showToast("Image downloaded."); return; } const response = await fetch("/api/download", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url: url, mode: currentMode, quality: currentQuality }) }); const data = await response.json(); if (!response.ok) throw new Error(data.error || "Download could not be started."); if (!data.job_id) throw new Error("Server did not return a download job ID."); createJobCard(data.job_id); $("#status").textContent = "Download started. You can paste another URL."; showToast("Download started."); $("#url").focus(); $("#url").select(); } catch (error) { $("#status").textContent = error.message; showToast(error.message); } finally { button.disabled = false; button.textContent = imageMode ? "🖼 Download Image" : (currentMode === "audio" ? "🎵 Start MP3 Download" : `⬇ Start ${currentQuality}p MP4 Download`); } }\n''',
    "image download handler",
)
replace_once(
    html,
    '''result.innerHTML = `${data.thumbnail ? `<img class="thumb" src="${escapeHtml(data.thumbnail)}" alt="Media thumbnail">` : ""}<div class="result-title">${escapeHtml(data.title || "Untitled media")}</div><div class="result-meta">${data.extractor ? `Platform: ${escapeHtml(data.extractor)}<br>` : ""}${data.domain ? `Website: ${escapeHtml(data.domain)}<br>` : ""}Available source qualities: ${escapeHtml(qualityText)}${data.original_height ? `<br>Detected maximum: ${escapeHtml(data.original_height)}p` : ""}${selectedQualityWarning}</div><div class="download-area"><button class="btn download-btn" id="downloadBtn" type="button">${currentMode === "audio" ? "🎵 Start MP3 Download" : `⬇ Start ${currentQuality}p MP4 Download`}</button></div>`; result.hidden = false; $("#downloadBtn").addEventListener("click", startDownload); }\n''',
    '''result.innerHTML = `${data.thumbnail ? `<img class="thumb" src="${escapeHtml(data.thumbnail)}" alt="Media thumbnail">` : ""}<div class="result-title">${escapeHtml(data.title || "Untitled media")}</div><div class="result-meta">${data.extractor ? `Platform: ${escapeHtml(data.extractor)}<br>` : ""}${data.domain ? `Website: ${escapeHtml(data.domain)}<br>` : ""}Available source qualities: ${escapeHtml(qualityText)}${data.original_height ? `<br>Detected maximum: ${escapeHtml(data.original_height)}p` : ""}${selectedQualityWarning}</div><div class="download-area"><button class="btn download-btn" id="downloadBtn" type="button">${imageMode ? "🖼 Download Image" : (currentMode === "audio" ? "🎵 Start MP3 Download" : `⬇ Start ${currentQuality}p MP4 Download`)}</button></div>`; result.hidden = false; $("#downloadBtn").addEventListener("click", startDownload); }\n''',
    "image button label",
)

# 6) Keep the Windows controls fixed just below the fetch area instead of
#    attaching them to the scrolling document flow.
launcher = ROOT / "windows" / "launcher.py"
replace_once(
    launcher,
    'position:fixed; left:50%; bottom:16px;',
    'position:fixed; left:50%; top:148px;',
    "fixed Windows toolbar position",
)
replace_once(
    launcher,
    '@media(max-width:700px){#avd-native-tools{left:10px;right:10px;transform:none;bottom:10px}.avd-folder-label{max-width:55vw}}',
    '@media(max-width:700px){#avd-native-tools{left:10px;right:10px;transform:none;top:126px}.avd-folder-label{max-width:55vw}}',
    "mobile Windows toolbar position",
)

print("Release patch applied successfully.")
