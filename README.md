# All Video Downloader Without Watermark

A standalone **Flask + yt-dlp** downloader project with Android and Windows builds, a public download website, and automatic versioned releases.

## Official download page

The website always points its Android and Windows buttons to the latest GitHub release assets, so the download links do not need to be changed manually for every new release.

## What is included

- Windows desktop application
- Android APK
- Flask downloader engine
- yt-dlp extractor architecture for broad public-media site coverage
- FFmpeg support for media merging/conversion
- 4K selection when the source actually provides a compatible 2160p format
- Source-title-based filenames
- Windows update notification
- Android update notification
- Automatic versioned GitHub releases from the main branch
- GitHub Pages download website
- Website auto-refresh/version checking

## Automatic app updates

Installed Windows and Android builds check the repository's latest published release when the app starts. If a newer version is available, the user is notified and can choose to update.

The release workflow automatically generates a new version number for future builds. The Android version code is also increased automatically so newer APKs can be installed as updates. The Windows installer and launcher use the same generated version.

The website's Android and Windows download buttons use GitHub's `releases/latest/download/...` URLs, so they automatically follow the newest published release. GitHub's release API provides the latest published release and its assets.

## Run on Windows for development

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

## Architecture notes

- yt-dlp provides broad extractor coverage, but no software can truthfully guarantee every website forever; sites can change or block extraction.
- DRM-protected, private, login-only and paywalled media are not bypassed.
- The backend selects a real stream at or below the requested height; it does not upscale a low-resolution source and call it native 4K.
- Exact final file size is known after the file is produced.
- The public website is a static download/presentation page. It cannot silently install native applications.
- Native Windows and Android applications handle their own update checks.

## Release workflow

Every push to `main` runs the Android + Windows build workflow. The workflow generates a version based on the GitHub Actions run number, builds both platforms, and publishes a new GitHub Release with the APK and Windows installer.

This means future app releases follow the same update path without manually changing the download buttons on the website.

## Responsible use

Download only media that you have permission to save. Do not use the project to bypass DRM, private access controls, paywalls, or other restrictions, and respect copyright and the terms of the source service.

## Developer

**Azan Khan** — 10th class student and independent developer building this project as a practical software-learning project.
