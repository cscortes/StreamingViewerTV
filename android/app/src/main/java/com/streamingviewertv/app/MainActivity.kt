package com.streamingviewertv.app

import android.content.Intent
import android.graphics.Bitmap
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.ProgressBar
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat

class MainActivity : AppCompatActivity() {
    private lateinit var webView: WebView
    private lateinit var statusText: TextView
    private lateinit var progressBar: ProgressBar
    private val handler = Handler(Looper.getMainLooper())
    private var pollAttempts = 0

    private val pollRunnable = object : Runnable {
        override fun run() {
            if (ViewerService.isServerReady()) {
                showWebView()
                return
            }
            pollAttempts += 1
            if (pollAttempts > MAX_POLLS) {
                statusText.text = getString(R.string.server_start_failed)
                progressBar.visibility = View.GONE
                return
            }
            statusText.text = getString(R.string.starting_server, pollAttempts)
            handler.postDelayed(this, POLL_MS)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        webView = findViewById(R.id.webView)
        statusText = findViewById(R.id.statusText)
        progressBar = findViewById(R.id.progressBar)

        configureWebView()

        ContextCompat.startForegroundService(
            this,
            Intent(this, ViewerService::class.java).setAction(ViewerService.ACTION_START),
        )

        statusText.text = getString(R.string.starting_server, 0)
        handler.post(pollRunnable)
    }

    private fun configureWebView() {
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            mediaPlaybackRequiresUserGesture = false
            mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
            cacheMode = WebSettings.LOAD_DEFAULT
        }
        webView.webChromeClient = WebChromeClient()
        webView.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView?, url: String?, favicon: Bitmap?) {
                progressBar.visibility = View.VISIBLE
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                progressBar.visibility = View.GONE
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?,
            ) {
                if (request?.isForMainFrame == true) {
                    statusText.visibility = View.VISIBLE
                    statusText.text = getString(R.string.webview_error)
                    webView.visibility = View.GONE
                }
            }
        }
    }

    private fun showWebView() {
        statusText.visibility = View.GONE
        progressBar.visibility = View.GONE
        webView.visibility = View.VISIBLE
        webView.loadUrl(ViewerService.SERVER_URL)
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (webView.visibility == View.VISIBLE && webView.canGoBack()) {
            webView.goBack()
        } else {
            @Suppress("DEPRECATION")
            super.onBackPressed()
        }
    }

    override fun onDestroy() {
        handler.removeCallbacks(pollRunnable)
        super.onDestroy()
    }

    companion object {
        private const val POLL_MS = 500L
        private const val MAX_POLLS = 120
    }
}
