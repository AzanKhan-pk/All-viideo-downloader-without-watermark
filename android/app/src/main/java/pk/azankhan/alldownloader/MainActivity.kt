package pk.azankhan.alldownloader

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.util.Log
import android.view.ActionMode
import android.view.Menu
import android.view.MenuItem
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.core.content.FileProvider
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors
import org.json.JSONObject

class MainActivity : Activity() {
    private lateinit var webView: WebView
    private val executor = Executors.newFixedThreadPool(2)
    private val port = 5000
    private val currentVersion = "1.0.7"
    private val releaseApi = "https://api.github.com/repos/AzanKhan-pk/All-viideo-downloader-without-watermark/releases/latest"

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        try {
            webView = WebView(this)
            setContentView(webView)
            configureWebView()
            startPythonServer()
            checkForUpdate()
        } catch (e: Throwable) {
            Log.e("AVD", "Application startup failed", e)
            showStartupError(e)
        }
    }

    private fun showStartupError(error: Throwable) {
        try {
            val text = TextView(this).apply {
                text = "All Video Downloader could not start.\n\n${error.javaClass.simpleName}: ${error.message ?: "Unknown startup error"}"
                textSize = 16f
                setPadding(48, 48, 48, 48)
                isTextSelectable = true
            }
            setContentView(text)
        } catch (_: Throwable) {
            Toast.makeText(this, "Downloader startup failed", Toast.LENGTH_LONG).show()
            finish()
        }
    }

    private fun ensurePythonStarted(): Boolean {
        return try {
            if (!Python.isStarted()) Python.start(AndroidPlatform(this))
            true
        } catch (e: Throwable) {
            Log.e("AVD", "Python runtime failed to start", e)
            runOnUiThread { showStartupError(e) }
            false
        }
    }

    private fun configureWebView() {
        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean = false
            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                enableTextSelection()
            }
        }
        webView.webChromeClient = WebChromeClient()
        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.settings.allowFileAccess = true
        webView.settings.allowContentAccess = true
        webView.settings.mediaPlaybackRequiresUserGesture = false
        webView.isLongClickable = true
        webView.setHapticFeedbackEnabled(true)
        webView.setOnLongClickListener { false }
        webView.isFocusable = true
        webView.isFocusableInTouchMode = true
    }

    private fun enableTextSelection() {
        val js = """
            (() => {
              const style = document.createElement('style');
              style.id = 'avd-android-selection';
              style.textContent = `
                html, body, body * { -webkit-user-select: text !important; user-select: text !important; }
                button, a, input, textarea, select { -webkit-user-select: text !important; user-select: text !important; }
              `;
              const old = document.getElementById('avd-android-selection');
              if (old) old.remove();
              document.head.appendChild(style);
            })();
        """.trimIndent()
        webView.evaluateJavascript(js, null)
    }

    private fun copyAssetTree(assetPath: String, target: File) {
        val children = assets.list(assetPath) ?: emptyArray()
        if (children.isEmpty()) {
            target.parentFile?.mkdirs()
            assets.open(assetPath).use { input -> target.outputStream().use { input.copyTo(it) } }
            return
        }
        target.mkdirs()
        for (child in children) copyAssetTree("$assetPath/$child", File(target, child))
    }

    private fun prepareOriginalProject(): File {
        val root = File(filesDir, "avd_runtime")
        root.mkdirs()
        copyAssetTree("original", root)
        return root
    }

    private fun startPythonServer() {
        if (!ensurePythonStarted()) return
        executor.execute {
            try {
                val root = prepareOriginalProject()
                Python.getInstance().getModule("embedded_server").callAttr("start", root.absolutePath, port)
            } catch (e: Throwable) {
                Log.e("AVD", "Python server failed", e)
                runOnUiThread { showStartupError(e) }
            }
        }
        executor.execute {
            repeat(120) {
                try {
                    URL("http://127.0.0.1:$port/api/health").openConnection().apply {
                        connectTimeout = 500
                        readTimeout = 500
                    }.getInputStream().close()
                    runOnUiThread { if (::webView.isInitialized) webView.loadUrl("http://127.0.0.1:$port/") }
                    return@execute
                } catch (_: Throwable) {
                    Thread.sleep(250)
                }
            }
            runOnUiThread { showStartupError(IllegalStateException("The local downloader service did not become ready.")) }
        }
    }

    private fun version(v: String): List<Int> = v.trimStart('v').split('.').map { it.toIntOrNull() ?: 0 }.take(3).let { it + List(3 - it.size) { 0 } }

    private fun checkForUpdate() {
        executor.execute {
            try {
                val conn = URL(releaseApi).openConnection() as HttpURLConnection
                conn.setRequestProperty("User-Agent", "All-Video-Downloader")
                conn.connectTimeout = 5000
                conn.readTimeout = 5000
                val release = JSONObject(conn.inputStream.bufferedReader().use { it.readText() })
                val latest = release.optString("tag_name")
                val assets = release.optJSONArray("assets") ?: return@execute
                var apkUrl: String? = null
                for (i in 0 until assets.length()) {
                    val asset = assets.getJSONObject(i)
                    if (asset.optString("name").endsWith(".apk", true)) { apkUrl = asset.optString("browser_download_url"); break }
                }
                if (version(latest) > version(currentVersion) && !apkUrl.isNullOrBlank()) {
                    runOnUiThread {
                        AlertDialog.Builder(this).setTitle("New update available")
                            .setMessage("Version $latest is available. Update now?")
                            .setNegativeButton("Later", null)
                            .setPositiveButton("Update") { _, _ -> downloadUpdate(apkUrl!!) }.show()
                    }
                }
            } catch (_: Throwable) { }
        }
    }

    private fun launchApkInstaller(apk: File) {
        try {
            val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", apk)
            val installIntent = Intent(Intent.ACTION_INSTALL_PACKAGE).apply {
                data = uri
                type = "application/vnd.android.package-archive"
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            }
            startActivity(installIntent)
        } catch (e: Throwable) {
            Log.e("AVD", "APK installer launch failed", e)
            runOnUiThread { Toast.makeText(this, "Android could not open the APK installer: ${e.message}", Toast.LENGTH_LONG).show() }
        }
    }

    private fun downloadUpdate(url: String) {
        executor.execute {
            try {
                val apk = File(cacheDir, "All-Video-Downloader-Update.apk")
                if (apk.exists()) apk.delete()
                URL(url).openStream().use { input -> apk.outputStream().use { output -> input.copyTo(output) } }
                if (!apk.exists() || apk.length() < 100_000L) throw IllegalStateException("Downloaded APK is incomplete")
                runOnUiThread {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && !packageManager.canRequestPackageInstalls()) {
                        startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName")))
                        Toast.makeText(this, "Allow installs from this app, then tap Update again.", Toast.LENGTH_LONG).show()
                    } else {
                        launchApkInstaller(apk)
                    }
                }
            } catch (e: Throwable) {
                Log.e("AVD", "Update download failed", e)
                runOnUiThread { Toast.makeText(this, "Update download failed: ${e.message}", Toast.LENGTH_LONG).show() }
            }
        }
    }

    override fun onBackPressed() { if (::webView.isInitialized && webView.canGoBack()) webView.goBack() else super.onBackPressed() }

    override fun onDestroy() {
        try { if (Python.isStarted()) Python.getInstance().getModule("embedded_server").callAttr("stop") } catch (_: Throwable) {}
        executor.shutdownNow()
        if (::webView.isInitialized) webView.destroy()
        super.onDestroy()
    }
}
