import os

# Keep WebView2 on the software ANGLE path for legacy GPUs, but do NOT disable
# Chromium's compositor. The compositor itself is part of WebView2's normal
# WinForms input/presentation path, and disabling it can create a different
# host presentation path than the one pywebview expects.
os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
    "--use-gl=angle "
    "--use-angle=swiftshader "
    "--disable-features=CalculateNativeWinOcclusion"
)
