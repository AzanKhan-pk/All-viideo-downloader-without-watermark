import os
from core_app import app
import media_features  # registers TikTok/Pinterest media routes

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
