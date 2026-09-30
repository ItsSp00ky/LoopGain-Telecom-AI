package com.loopgain.kpimonitor

import android.annotation.SuppressLint
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Switch
import android.widget.TextView
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.widget.Toolbar
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Loads one page of the existing `platform_app` Streamlit shell (chosen via
 * [EXTRA_PATH]) inside a pull-to-refresh WebView with an auto-refresh "live
 * tracking" toggle, so it can be checked/tracked from a phone.
 */
class DetailActivity : AppCompatActivity() {

    private lateinit var webView: WebView
    private lateinit var swipeRefresh: SwipeRefreshLayout
    private lateinit var statusLabel: TextView
    private lateinit var liveTrackingSwitch: Switch

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
        setContentView(R.layout.activity_detail)

        val title = intent.getStringExtra(EXTRA_TITLE) ?: getString(R.string.app_name)
        val urlPath = intent.getStringExtra(EXTRA_PATH).orEmpty()

        val toolbar = findViewById<Toolbar>(R.id.toolbar)
        toolbar.title = title
        setSupportActionBar(toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        toolbar.setNavigationOnClickListener { onBackPressedDispatcher.onBackPressed() }

        webView = findViewById(R.id.webView)
        swipeRefresh = findViewById(R.id.swipeRefresh)
        statusLabel = findViewById(R.id.statusLabel)
        liveTrackingSwitch = findViewById(R.id.liveTrackingSwitch)

        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.settings.useWideViewPort = true
        webView.settings.loadWithOverviewMode = true
        webView.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView?, url: String?) {
                super.onPageFinished(view, url)
                swipeRefresh.isRefreshing = false
                statusLabel.text = getString(R.string.last_updated_prefix) + timeFormat.format(Date())
            }
        }

        swipeRefresh.setOnRefreshListener { webView.reload() }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                if (webView.canGoBack()) webView.goBack() else {
                    isEnabled = false
                    onBackPressedDispatcher.onBackPressed()
                }
            }
        })

        val prefs = getSharedPreferences("kpi_monitor", MODE_PRIVATE)
        val host = prefs.getString(DashboardActivity.PREF_SERVER_HOST, getString(R.string.default_server_host))
            ?: getString(R.string.default_server_host)
        webView.loadUrl("$host/$urlPath".trimEnd('/'))

        autoRefreshHandler.postDelayed(autoRefreshRunnable, AUTO_REFRESH_INTERVAL_MS)
    }

    override fun onDestroy() {
        autoRefreshHandler.removeCallbacks(autoRefreshRunnable)
        super.onDestroy()
    }

    companion object {
        const val EXTRA_TITLE = "extra_title"
        const val EXTRA_PATH = "extra_path"
        private const val AUTO_REFRESH_INTERVAL_MS = 20_000L
    }
}
