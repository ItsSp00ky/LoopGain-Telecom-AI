package com.loopgain.kpimonitor

import android.annotation.SuppressLint
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.Switch
import android.widget.TextView
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Wraps the LoopGain Telecom AI Streamlit platform (Network KPI page by default)
 * in a native shell so it can be demoed, refreshed and "tracked" from a phone.
 *
 * Default target is the Android emulator's alias for the host machine
 * (10.0.2.2). For a physical phone on the same WiFi as the laptop running
 * `python run_platform.py`, type the laptop's LAN IP instead, e.g.
 * http://192.168.1.23:8510/network - no rebuild needed, it's saved on device.
 */
class MainActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var swipeRefresh: SwipeRefreshLayout
    private lateinit var serverUrlInput: EditText
    private lateinit var statusLabel: TextView
    private lateinit var liveTrackingSwitch: Switch

    private val prefs by lazy { getSharedPreferences("kpi_monitor", MODE_PRIVATE) }
    private val autoRefreshHandler = Handler(Looper.getMainLooper())
    private val timeFormat = SimpleDateFormat("HH:mm:ss", Locale.getDefault())

    private val autoRefreshRunnable = object : Runnable {
        override fun run() {
            if (liveTrackingSwitch.isChecked) {
                webView.reload()
            }
            autoRefreshHandler.postDelayed(this, AUTO_REFRESH_INTERVAL_MS)
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        webView = findViewById(R.id.webView)
        swipeRefresh = findViewById(R.id.swipeRefresh)
        serverUrlInput = findViewById(R.id.serverUrlInput)
        statusLabel = findViewById(R.id.statusLabel)
        liveTrackingSwitch = findViewById(R.id.liveTrackingSwitch)

        val savedUrl = prefs.getString(PREF_SERVER_URL, getString(R.string.default_server_url))
        serverUrlInput.setText(savedUrl)

        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.settings.useWideViewPort = true
        webView.settings.loadWithOverviewMode = true
        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                swipeRefresh.isRefreshing = false
                updateStatusLabel()
            }
        }

        swipeRefresh.setOnRefreshListener { webView.reload() }

        findViewById<Button>(R.id.connectButton).setOnClickListener {
            loadServer(serverUrlInput.text.toString())
        }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.canGoBack()) webView.goBack() else {
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                }
            }
        })

        loadServer(savedUrl ?: getString(R.string.default_server_url))
        autoRefreshHandler.postDelayed(autoRefreshRunnable, AUTO_REFRESH_INTERVAL_MS)
    }

    private fun loadServer(url: String) {
        val target = if (url.startsWith("http")) url else "http://$url"
        prefs.edit().putString(PREF_SERVER_URL, target).apply()
        webView.loadUrl(target)
    }

    private fun updateStatusLabel() {
        statusLabel.text = getString(R.string.last_updated_prefix) + timeFormat.format(Date())
    }

    override fun onDestroy() {
        autoRefreshHandler.removeCallbacks(autoRefreshRunnable)
        super.onDestroy()
    }

    companion object {
        private const val PREF_SERVER_URL = "server_url"
        private const val AUTO_REFRESH_INTERVAL_MS = 20_000L
    }
}
