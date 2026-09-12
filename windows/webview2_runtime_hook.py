import os

# Legacy GPUs can leave WebView2 with a black client area when Chromium tries
# to use the hardware ANGLE/D3D path. Force Chromium's current software
# renderer instead. SwiftShader runs on the CPU, so the app does not depend
# on the old NVIDIA/Direct3D driver for WebView rendering.
os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = (
    "--use-gl=angle "
    "--use-angle=swiftshader "
    "--disable-gpu-compositing "
    "--disable-features=CalculateNativeWinOcclusion"
)
