package pk.azankhan.alldownloader

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.util.Log
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
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
    private val currentVersion = "1.0.4"
    private val releaseApi = "https://api.github.com/repos/AzanKhan-pk/All-viideo-downloader-without-watermark/releases/latest"

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        webView = WebView(this)
        setContentView(webView)
        configureWebView()
        startPythonServer()
        checkForUpdate()
    }

    private fun configureWebView() {
        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, request: WebResourceRequest?): Boolean = false
        }
        webView.webChromeClient = WebChromeClient()
        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.settings.allowFileAccess = true
        webView.settings.allowContentAccess = true
        webView.settings.mediaPlaybackRequiresUserGesture = false
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
        if (!Python.isStarted()) Python.start(AndroidPlatform(this))
        val root = prepareOriginalProject()
        executor.execute {
            try {
                Python.getInstance().getModule("embedded_server").callAttr("start", root.absolutePath, port)
            } catch (e: Exception) {
                Log.e("AVD", "Python server failed", e)
                runOnUiThread { Toast.makeText(this, "Downloader engine could not start", Toast.LENGTH_LONG).show() }
            }
        }
        executor.execute {
            repeat(80) {
                try {
                    URL("http://127.0.0.1:$port/api/health").openConnection().apply { connectTimeout = 500; readTimeout = 500 }.getInputStream().close()
                    runOnUiThread { webView.loadUrl("http://127.0.0.1:$port/") }
                    return@execute
                } catch (_: Exception) { Thread.sleep(250) }
            }
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
            } catch (_: Exception) { }
        }
    }

    private fun downloadUpdate(url: String) {
        executor.execute {
            try {
                val apk = File(cacheDir, "All-Video-Downloader-Update.apk")
                URL(url).openStream().use { input -> apk.outputStream().use { output -> input.copyTo(output) } }
                runOnUiThread {
                    if (android.os.Build.VERSION.SDK_INT >= 26 && !packageManager.canRequestPackageInstalls()) {
                        startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName")))
                        Toast.makeText(this, "Allow installs from this app, then press Update again.", Toast.LENGTH_LONG).show()
                    } else {
                        val uri = FileProvider.getUriForFile(this, "$packageName.fileprovider", apk)
                        startActivity(Intent(Intent.ACTION_VIEW).apply {
                            setDataAndType(uri, "application/vnd.android.package-archive")
                            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                        })
                    }
                }
            } catch (_: Exception) {
                runOnUiThread { Toast.makeText(this, "Update download failed", Toast.LENGTH_LONG).show() }
            }
        }
    }

    override fun onBackPressed() { if (webView.canGoBack()) webView.goBack() else super.onBackPressed() }

    override fun onDestroy() {
        try { if (Python.isStarted()) Python.getInstance().getModule("embedded_server").callAttr("stop") } catch (_: Exception) {}
        executor.shutdownNow()
        webView.destroy()
        super.onDestroy()
    }
}
