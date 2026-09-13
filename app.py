import os
from core_app import app
import runtime_patches  # safe URL-aware extractor and Windows download defaults
import media_features  # registers TikTok/Pinterest media routes
import media_url_compat  # accepts Pinterest pin.it share links
import location_features  # registers native download-location routes
import history_features  # persists completed downloads across app restarts
import ui_patches  # injects persistent controls while preserving the original progress UI

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
