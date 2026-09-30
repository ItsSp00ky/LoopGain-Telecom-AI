package com.loopgain.kpimonitor

import android.annotation.SuppressLint
import android.content.Intent
import android.graphics.Bitmap
import androidx.core.view.ViewCompat
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.View
import android.view.ViewGroup
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.TextView
import androidx.activity.OnBackPressedCallback
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.widget.SwitchCompat
import androidx.appcompat.widget.Toolbar
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Existing module WebView, with native loading and recoverable failure states. */
class DetailActivity : AppCompatActivity() {
    private enum class PageState { LOADING, CONTENT, ERROR }

    private lateinit var webView: WebView
    private lateinit var swipeRefresh: SwipeRefreshLayout
    private lateinit var statusLabel: TextView
    private lateinit var liveTrackingSwitch: SwitchCompat
    private lateinit var loadingState: View
    private lateinit var errorState: View
    private var pageState = PageState.LOADING
    private var requestedUrl = ""
    private var failedUrl: String? = null
    private val handler = Handler(Looper.getMainLooper())
    private val timeFormat = SimpleDateFormat("HH:mm:ss", Locale.getDefault())

    private val loadTimeout = Runnable {
        if (pageState == PageState.LOADING) {
            showError(R.string.timeout_error_title, getString(R.string.timeout_error_body))
            webView.stopLoading()
        }
    }
    private val autoRefresh = object : Runnable {
        override fun run() {
            // Do not interrupt an in-flight load or repeatedly replace the retry screen.
            if (liveTrackingSwitch.isChecked && pageState == PageState.CONTENT) webView.reload()
            handler.postDelayed(this, AUTO_REFRESH_INTERVAL_MS)
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_detail)
        ViewCompat.setAccessibilityHeading(findViewById(R.id.errorTitle), true)
        val toolbar = findViewById<Toolbar>(R.id.toolbar)
        toolbar.title = intent.getStringExtra(EXTRA_TITLE) ?: getString(R.string.app_name)
        setSupportActionBar(toolbar)
        supportActionBar?.setDisplayHomeAsUpEnabled(true)
        toolbar.setNavigationOnClickListener { onBackPressedDispatcher.onBackPressed() }

        webView = findViewById(R.id.webView)
        swipeRefresh = findViewById(R.id.swipeRefresh)
        statusLabel = findViewById(R.id.statusLabel)
        liveTrackingSwitch = findViewById(R.id.liveTrackingSwitch)
        loadingState = findViewById(R.id.loadingState)
        errorState = findViewById(R.id.errorState)
        liveTrackingSwitch.setOnCheckedChangeListener { _, _ -> updateRefreshHint() }
        swipeRefresh.setColorSchemeResources(R.color.brand_blue, R.color.brand_teal)
        swipeRefresh.setProgressBackgroundColorSchemeResource(R.color.surface)
        swipeRefresh.setOnChildScrollUpCallback { _, _ -> webView.canScrollVertically(-1) }
        webView.setBackgroundColor(getColor(R.color.background))
        webView.settings.javaScriptEnabled = true
        webView.settings.domStorageEnabled = true
        webView.settings.useWideViewPort = true
        webView.settings.loadWithOverviewMode = true
        webView.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView, url: String?, favicon: Bitmap?) {
                // Some WebView versions deliver HTTP failure before the start callback.
                if (pageState == PageState.ERROR && url == failedUrl) return
                failedUrl = null
                if (!url.isNullOrBlank()) requestedUrl = url
                showLoading()
            }

            override fun onPageFinished(view: WebView, url: String?) {
                // WebView also finishes failed navigations; never overwrite the error state.
                if (pageState != PageState.LOADING) return
                handler.removeCallbacks(loadTimeout)
                pageState = PageState.CONTENT
                updateRefreshHint()
                swipeRefresh.isRefreshing = false
                swipeRefresh.isEnabled = true
                swipeRefresh.visibility = View.VISIBLE
                loadingState.visibility = View.GONE
                errorState.visibility = View.GONE
                statusLabel.setTextColor(getColor(R.color.text_secondary))
                // A document load does not certify backend health or KPI freshness.
                statusLabel.text = getString(R.string.page_loaded_at, timeFormat.format(Date()))
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame && pageState != PageState.ERROR) {
                    showError(R.string.connection_error_title, getString(R.string.connection_error_body), request.url.toString())
                }
            }

            override fun onReceivedHttpError(view: WebView, request: WebResourceRequest, response: WebResourceResponse) {
                // A missing image/iframe must not hide an otherwise usable page.
                if (request.isForMainFrame) {
                    showError(R.string.http_error_title, getString(R.string.http_error_body, response.statusCode), request.url.toString())
                }
            }
        }

        swipeRefresh.setOnRefreshListener { webView.reload() }
        findViewById<View>(R.id.retryButton).setOnClickListener {
            failedUrl = null
            showLoading()
            webView.loadUrl(requestedUrl)
        }
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
        val urlPath = intent.getStringExtra(EXTRA_PATH).orEmpty()
        findViewById<View>(R.id.aiAssistantBar).visibility = if (urlPath == "assistants") View.GONE else View.VISIBLE
        findViewById<View>(R.id.aiAssistantButton).setOnClickListener {
            startActivity(Intent(this, DetailActivity::class.java)
                .putExtra(EXTRA_TITLE, getString(R.string.page_assistants_title))
                .putExtra(EXTRA_PATH, "assistants"))
        }
        requestedUrl = "$host/$urlPath".trimEnd('/')
        showLoading()
        webView.loadUrl(requestedUrl)
    }

    private fun showLoading() {
        pageState = PageState.LOADING
        updateRefreshHint()
        errorState.visibility = View.GONE
        loadingState.visibility = View.VISIBLE
        swipeRefresh.visibility = View.INVISIBLE
        swipeRefresh.isRefreshing = false
        swipeRefresh.isEnabled = false
        statusLabel.setTextColor(getColor(R.color.text_secondary))
        statusLabel.setText(R.string.page_loading)
        handler.removeCallbacks(loadTimeout)
        handler.postDelayed(loadTimeout, LOAD_TIMEOUT_MS)
    }

    private fun showError(title: Int, message: String, url: String = requestedUrl) {
        failedUrl = url
        pageState = PageState.ERROR
        updateRefreshHint()
        handler.removeCallbacks(loadTimeout)
        swipeRefresh.isRefreshing = false
        swipeRefresh.isEnabled = false
        swipeRefresh.visibility = View.INVISIBLE
        loadingState.visibility = View.GONE
        errorState.visibility = View.VISIBLE
        findViewById<TextView>(R.id.errorTitle).setText(title)
        findViewById<TextView>(R.id.errorMessage).text = message
        statusLabel.setTextColor(getColor(R.color.error))
        statusLabel.setText(R.string.page_unavailable)
    }

    private fun updateRefreshHint() {
        val hint = when (pageState) {
            PageState.ERROR -> R.string.refresh_paused_hint
            PageState.LOADING -> R.string.refresh_loading_hint
            PageState.CONTENT -> if (liveTrackingSwitch.isChecked) R.string.refresh_hint else R.string.refresh_manual_hint
        }
        findViewById<TextView>(R.id.refreshHint).setText(hint)
    }

    override fun onResume() {
        super.onResume()
        webView.onResume()
        handler.removeCallbacks(autoRefresh)
        handler.postDelayed(autoRefresh, AUTO_REFRESH_INTERVAL_MS)
    }

    override fun onPause() {
        handler.removeCallbacks(autoRefresh)
        webView.onPause()
        super.onPause()
    }

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        webView.stopLoading()
        (webView.parent as? ViewGroup)?.removeView(webView)
        webView.destroy()
        super.onDestroy()
    }

    companion object {
        const val EXTRA_TITLE = "extra_title"
        const val EXTRA_PATH = "extra_path"
        private const val AUTO_REFRESH_INTERVAL_MS = 20_000L
        private const val LOAD_TIMEOUT_MS = 30_000L
    }
}
