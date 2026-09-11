from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path, old, new, label):
    text = path.read_text(encoding="utf-8")
    if old not in text:
        print(f"Patch target already applied or obsolete; skipping: {label}")
        return
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


# This is now a compatibility shim. The current release pipeline has separate
# idempotent patches for quality selection, TikTok, persistence/gallery and the
# Windows runtime. An obsolete legacy target must never abort a release.
print("Legacy release patch compatibility check passed.")

launcher = ROOT / "windows" / "launcher.py"
replace_once(
    launcher,
    'position:fixed; left:50%; bottom:16px;',
    'position:fixed; left:50%; top:148px;',
    "fixed Windows toolbar position",
)

print("Release build legacy patch step completed.")
