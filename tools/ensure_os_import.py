from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
text = APP.read_text(encoding="utf-8")

if not any(line.strip() == "import os" for line in text.splitlines()[:20]):
    text = "import os\n" + text
    APP.write_text(text, encoding="utf-8")
    print("Added missing import os to app.py.")
else:
    print("app.py already has import os.")
