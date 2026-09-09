# All Video Downloader Without Watermark

A standalone Flask + yt-dlp public-media downloader starter.

## Run on Windows

1. Install Python 3.11+.
2. Install FFmpeg and make sure `ffmpeg` is in PATH (required for many video merges/audio conversions).
3. Open PowerShell in this folder.
4. Run:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

5. Open `http://127.0.0.1:5000`.

## Important architecture notes

- yt-dlp provides broad extractor coverage, but no software can truthfully guarantee every website.
- DRM-protected, private, login-only and paywalled media are not bypassed.
- The backend selects a real stream at or below the requested height; it does not upscale.
- Exact final file size is known only after the file is produced. Before download, a size can be estimated but should not be presented as guaranteed.
- The current progress UI reports actual completed file size after processing. For byte-level live progress/speed, the backend should be moved to a job/streaming architecture (SSE/WebSocket + progress hooks).
- PWA installation is supported by the manifest. A website cannot silently install a Windows EXE or iOS/Android native app.

## Future production modules

Authentication/history, Google OAuth, persistent jobs, SSE progress, Redis/queue workers, rate limiting, cleanup, object storage, FFmpeg validation, and a native desktop/mobile shell can be added without changing the main UI.
