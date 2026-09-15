import os
from core_app import app
import runtime_patches  # safe URL-aware extractor and Windows download defaults
import media_features  # registers TikTok/Pinterest media routes
import image_quality_patch  # focused image de-duplication and broad public image extraction
import social_html_fallback  # HTML fallback for TikTok photo and Pinterest media
import media_quality_patch  # focused quality, preview thumbnails, and image extraction
import media_resilience_patch  # rejects HTML-as-media, supports Pinterest HLS, hardens preview/quality
import media_url_compat  # accepts Pinterest pin.it share links
import conversion_audio_patch  # live FFmpeg conversion progress and Pinterest audio merge
import location_features  # registers native download-location routes
import history_features  # persists completed downloads across app restarts
import ui_patches  # injects persistent controls while preserving the original progress UI
import final_media_reliability_patch  # existing reliability layer
import final_media_reliability_v2  # final v2 fixes for audio, images, size and folder UI

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
