import os

# Use Chromium's software WARP renderer on legacy/problematic Windows GPUs.
# This is applied before launcher.py imports pywebview, so the existing
# setdefault() does not overwrite it.
os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
    "--use-angle=warp "
    "--disable-gpu-compositing "
    "--disable-features=CalculateNativeWinOcclusion"
)
