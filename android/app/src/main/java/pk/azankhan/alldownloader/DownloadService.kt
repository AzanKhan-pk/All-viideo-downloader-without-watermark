package pk.azankhan.alldownloader

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONArray
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors

class DownloadService : Service() {
    companion object {
        const val CHANNEL_ID = "avd_downloads"
        const val NOTIFICATION_ID = 4101
        const val PORT = 5000
    }

    private val executor = Executors.newFixedThreadPool(2)
    @Volatile private var stopping = false

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForegroundNow("All Video Downloader", "Download service is ready", 0, false)
        startPythonServer()
        startNotificationPolling()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Downloads",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Video and image download progress"
                setShowBadge(true)
            }
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    private fun startForegroundNow(title: String, text: String, progress: Int, indeterminate: Boolean) {
        val openIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val pendingFlags = PendingIntent.FLAG_UPDATE_CURRENT or
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) PendingIntent.FLAG_IMMUTABLE else 0
        val pending = PendingIntent.getActivity(this, 4102, openIntent, pendingFlags)
        val builder = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(pk.azankhan.alldownloader.R.drawable.ic_launcher)
            .setContentTitle(title)
            .setContentText(text)
            .setContentIntent(pending)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setCategory(NotificationCompat.CATEGORY_PROGRESS)
            .setPriority(NotificationCompat.PRIORITY_LOW)
        if (indeterminate) {
            builder.setProgress(100, 0, true)
        } else {
            builder.setProgress(100, progress.coerceIn(0, 100), false)
        }
        val notification = builder.build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ServiceCompat.startForeground(
                this,
                NOTIFICATION_ID,
                notification,
                android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
            )
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
    }

    private fun prepareOriginalProject(): File {
        val root = File(filesDir, "avd_runtime")
        root.mkdirs()
        copyAssetTree("original", root)
        return root
    }

    private fun copyAssetTree(assetPath: String, target: File) {
        val children = assets.list(assetPath) ?: emptyArray()
        if (children.isEmpty()) {
            target.parentFile?.mkdirs()
            assets.open(assetPath).use { input -> target.outputStream().use { output -> input.copyTo(output) } }
            return
        }
        target.mkdirs()
        for (child in children) copyAssetTree("$assetPath/$child", File(target, child))
    }

    private fun startPythonServer() {
        executor.execute {
            try {
                if (!Python.isStarted()) Python.start(AndroidPlatform(this))
                val root = prepareOriginalProject()
                Python.getInstance().getModule("embedded_server").callAttr("start", root.absolutePath, PORT)
            } catch (e: Throwable) {
                Log.e("AVD", "Background Python server failed", e)
            }
        }
    }

    private fun startNotificationPolling() {
        executor.execute {
            while (!stopping) {
                try {
                    val connection = URL("http://127.0.0.1:$PORT/api/jobs").openConnection() as HttpURLConnection
                    connection.connectTimeout = 1200
                    connection.readTimeout = 1200
                    val body = connection.inputStream.bufferedReader().use { it.readText() }
                    connection.disconnect()
                    val jobs = JSONArray(org.json.JSONObject(body).optJSONArray("jobs")?.toString() ?: "[]")
                    var active: org.json.JSONObject? = null
                    for (i in 0 until jobs.length()) {
                        val job = jobs.optJSONObject(i) ?: continue
                        val status = job.optString("status")
                        if (status in setOf("queued", "starting", "downloading", "processing", "converting")) {
                            active = job
                            break
                        }
                    }
                    if (active != null) {
                        val percent = active!!.optDouble("percentage", 0.0).toInt().coerceIn(0, 100)
                        val title = active!!.optString("title", "Downloading…")
                        val speed = active!!.optString("speed_text", "")
                        val total = active!!.optString("total_text", "")
                        val detail = if (speed.isNotBlank()) "$percent% • $speed • $total" else "$percent% • Downloading"
                        startForegroundNow(title, detail, percent, false)
                    } else {
                        startForegroundNow("All Video Downloader", "Ready for downloads", 0, false)
                    }
                } catch (_: Throwable) {
                    // The server may still be starting; retry without killing the service.
                }
                try { Thread.sleep(1000) } catch (_: InterruptedException) { break }
            }
        }
    }

    override fun onDestroy() {
        stopping = true
        try {
            if (Python.isStarted()) Python.getInstance().getModule("embedded_server").callAttr("stop")
        } catch (e: Throwable) {
            Log.w("AVD", "Python service stop failed", e)
        }
        executor.shutdownNow()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
