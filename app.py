import os
from core_app import app
import runtime_patches  # safe URL-aware extractor and Windows download defaults
import media_features  # registers TikTok/Pinterest media routes
import location_features  # registers native download-location routes

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
