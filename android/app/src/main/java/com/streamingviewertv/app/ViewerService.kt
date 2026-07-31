package com.streamingviewertv.app

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
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

/**
 * Foreground service that embeds CPython via Chaquopy and runs the FastAPI viewer
 * on 127.0.0.1:8787 — same model as the desktop PyInstaller app.
 */
class ViewerService : Service() {
    private var serverThread: Thread? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_STOP -> {
                stopServer()
                stopSelf()
                return START_NOT_STICKY
            }
            else -> {
                startForeground(NOTIFICATION_ID, buildNotification())
                ensureCatalog()
                startServerIfNeeded()
            }
        }
        return START_STICKY
    }

    private fun ensureCatalog() {
        val home = filesDir
        val exportDir = File(home, "iptv_export")
        if (!exportDir.exists()) {
            exportDir.mkdirs()
        }
        val dest = File(exportDir, "viewer.db")
        if (dest.exists() && dest.length() > 0L) {
            return
        }
        try {
            assets.open("iptv_export/viewer.db").use { input ->
                FileOutputStream(dest).use { output -> input.copyTo(output) }
            }
            Log.i(TAG, "Copied viewer.db (${dest.length()} bytes) to ${dest.absolutePath}")
        } catch (e: Exception) {
            Log.e(TAG, "viewer.db missing from assets — run: make android-sync-db", e)
        }
    }

    private fun startServerIfNeeded() {
        if (serverStarted.get()) {
            return
        }
        serverThread = thread(name = "stream-viewer-uvicorn", isDaemon = true) {
            try {
                // Start Python on this thread so asyncio considers it the main thread.
                if (!Python.isStarted()) {
                    Python.start(AndroidPlatform(this@ViewerService))
                }

                val py = Python.getInstance()
                val launcher = py.getModule("android_launcher")
                serverStarted.set(true)
                // Blocks until the server stops.
                launcher.callAttr("start", SERVER_HOST, SERVER_PORT)
            } catch (e: Exception) {
                Log.e(TAG, "Failed to start FastAPI server", e)
                serverStarted.set(false)
                serverReady.set(false)
            }
        }

        thread(name = "stream-viewer-ready-poll", isDaemon = true) {
            repeat(120) {
                if (probeServer()) {
                    serverReady.set(true)
                    Log.i(TAG, "Server ready at $SERVER_URL")
                    return@thread
                }
                Thread.sleep(500)
            }
            Log.e(TAG, "Server did not become ready in time")
        }
    }

    private fun stopServer() {
        serverReady.set(false)
        serverStarted.set(false)
        // uvicorn has no clean remote stop from Kotlin; process death ends the loop.
        stopForeground(STOP_FOREGROUND_REMOVE)
    }

    private fun buildNotification(): Notification {
        createChannel()
        val openIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val stopIntent = PendingIntent.getService(
            this,
            1,
            Intent(this, ViewerService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.notification_title))
            .setContentText(getString(R.string.notification_text))
            .setSmallIcon(android.R.drawable.ic_media_play)
            .setContentIntent(openIntent)
            .addAction(0, getString(R.string.notification_stop), stopIntent)
            .setOngoing(true)
            .build()
    }

    private fun createChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val mgr = getSystemService(NotificationManager::class.java) ?: return
        val channel = NotificationChannel(
            CHANNEL_ID,
            getString(R.string.notification_channel),
            NotificationManager.IMPORTANCE_LOW,
        )
        mgr.createNotificationChannel(channel)
    }

    override fun onDestroy() {
        stopServer()
        super.onDestroy()
    }

    companion object {
        const val ACTION_START = "com.streamingviewertv.app.START"
        const val ACTION_STOP = "com.streamingviewertv.app.STOP"
        const val SERVER_HOST = "127.0.0.1"
        const val SERVER_PORT = 8787
        const val SERVER_URL = "http://$SERVER_HOST:$SERVER_PORT/"

        private const val TAG = "ViewerService"
        private const val CHANNEL_ID = "viewer_server"
        private const val NOTIFICATION_ID = 8787

        private val serverStarted = AtomicBoolean(false)
        private val serverReady = AtomicBoolean(false)

        fun isServerReady(): Boolean = serverReady.get() || probeServer()

        private fun probeServer(): Boolean {
            return try {
                val conn = URL(SERVER_URL).openConnection() as HttpURLConnection
                conn.connectTimeout = 500
                conn.readTimeout = 500
                conn.requestMethod = "GET"
                conn.connect()
                val code = conn.responseCode
                conn.disconnect()
                code in 200..399
            } catch (_: Exception) {
                false
            }
        }
    }
}
