package pk.azankhan.alldownloader

import android.annotation.SuppressLint
import android.app.Activity
import android.os.Bundle
import android.util.Log
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File
import java.util.concurrent.Executors

class MainActivity : Activity() {
    private lateinit var webView: WebView
    private val executor = Executors.newSingleThreadExecutor()
    private val port = 5000
    private var serverStarted = false

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        webView = WebView(this)
        setContentView(webView)
        configureWebView()
        startPythonServer()
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
                val py = Python.getInstance()
                py.getModule("embedded_server").callAttr("start", root.absolutePath, port)
            } catch (e: Exception) {
                Log.e("AVD", "Python server failed", e)
                runOnUiThread { Toast.makeText(this, "Downloader engine could not start", Toast.LENGTH_LONG).show() }
            }
        }
        waitForServer()
    }

    private fun waitForServer() {
        executor.execute {
            repeat(80) {
                try {
                    java.net.URL("http://127.0.0.1:$port/api/health").openConnection().apply { connectTimeout = 500; readTimeout = 500 }.getInputStream().close()
                    serverStarted = true
                    runOnUiThread { webView.loadUrl("http://127.0.0.1:$port/") }
                    return@execute
                } catch (_: Exception) { Thread.sleep(250) }
            }
            runOnUiThread { Toast.makeText(this, "Starting downloader engine took too long", Toast.LENGTH_LONG).show() }
        }
    }

    override fun onBackPressed() {
        if (webView.canGoBack()) webView.goBack() else super.onBackPressed()
    }

    override fun onDestroy() {
        try {
            if (Python.isStarted()) Python.getInstance().getModule("embedded_server").callAttr("stop")
        } catch (_: Exception) {}
        executor.shutdownNow()
        webView.destroy()
        super.onDestroy()
    }
}
