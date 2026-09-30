package com.loopgain.kpimonitor

import android.content.res.Configuration
import android.net.Uri
import android.widget.LinearLayout
import android.graphics.Typeface
import com.google.android.material.card.MaterialCardView
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors
import java.util.concurrent.Future
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import android.content.res.ColorStateList
import android.widget.GridLayout
import android.widget.ImageView
import android.widget.Toast
import com.google.android.material.dialog.MaterialAlertDialogBuilder
import com.google.android.material.textfield.TextInputLayout
import com.google.android.material.textfield.TextInputEditText
import android.content.Intent
import androidx.core.view.ViewCompat
import android.os.Bundle
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.widget.Toolbar

/**
 * Home screen: a grid of module cards, one per page of the existing
 * `platform_app` Streamlit shell. Tapping a card opens [DetailActivity],
 * which loads that module's page inside a native-feeling wrapper - this
 * gives the app real dashboard/navigation behaviour without having to
 * rebuild every module's backend as a native screen yet.
 */
class DashboardActivity : AppCompatActivity() {

    private data class ModulePage(val title: String, val subtitle: String, val urlPath: String, val colorRes: Int, val iconRes: Int)

    private val prefs by lazy { getSharedPreferences("kpi_monitor", MODE_PRIVATE) }

    private data class SummaryTile(val key: String, val id: Int, val label: Int, val route: String)
    private val summaryTiles = listOf(
        SummaryTile("kpi", R.id.summaryKpi, R.string.summary_kpi, "network"),
        SummaryTile("steering", R.id.summarySteering, R.string.summary_steering, "steering"),
        SummaryTile("traffic", R.id.summaryTraffic, R.string.summary_traffic, "network"),
        SummaryTile("gis", R.id.summaryGis, R.string.summary_gis, "gis"),
        SummaryTile("churn", R.id.summaryChurn, R.string.summary_churn, "churn"),
    )
    private val summaryExecutor = Executors.newSingleThreadExecutor()
    private var summaryJob: Future<*>? = null
    @Volatile private var summaryConnection: HttpURLConnection? = null
    private var summaryGeneration = 0
    private var lastSummaryFetch = 0L

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_dashboard)
        ViewCompat.setAccessibilityHeading(findViewById(R.id.dashboardHeading), true)
        ViewCompat.setAccessibilityHeading(findViewById(R.id.modulesHeading), true)
        setSupportActionBar(findViewById<Toolbar>(R.id.toolbar))

        val pages = listOf(
            ModulePage(getString(R.string.page_overview_title), getString(R.string.page_overview_subtitle), "", R.color.card_overview, R.drawable.ic_overview) to R.id.cardOverview,
            ModulePage(getString(R.string.page_network_title), getString(R.string.page_network_subtitle), "network", R.color.card_network, R.drawable.ic_network) to R.id.cardNetwork,
            ModulePage(getString(R.string.page_steering_title), getString(R.string.page_steering_subtitle), "steering", R.color.card_steering, R.drawable.ic_steering) to R.id.cardSteering,
            ModulePage(getString(R.string.page_gis_title), getString(R.string.page_gis_subtitle), "gis", R.color.card_gis, R.drawable.ic_gis) to R.id.cardGis,
            ModulePage(getString(R.string.page_churn_title), getString(R.string.page_churn_subtitle), "churn", R.color.card_churn, R.drawable.ic_churn) to R.id.cardChurn,
            ModulePage(getString(R.string.page_assistants_title), getString(R.string.page_assistants_subtitle), "assistants", R.color.card_assistants, R.drawable.ic_assistants) to R.id.cardAssistants,
        )

        for ((page, cardId) in pages) {
            val card = findViewById<View>(cardId)
            card.findViewById<TextView>(R.id.cardTitle).text = page.title
            card.findViewById<TextView>(R.id.cardSubtitle).text = page.subtitle
            card.findViewById<ImageView>(R.id.cardIcon).apply {
                setImageResource(page.iconRes)
                imageTintList = ColorStateList.valueOf(getColor(page.colorRes))
            }
            card.contentDescription = getString(R.string.card_open_description, page.title, page.subtitle)
            card.setOnClickListener {
                startActivity(
                    Intent(this, DetailActivity::class.java)
                        .putExtra(DetailActivity.EXTRA_TITLE, page.title)
                        .putExtra(DetailActivity.EXTRA_PATH, page.urlPath)
                )
            }
        }
        findViewById<View>(R.id.aiAssistantButton).setOnClickListener {
            startActivity(Intent(this, DetailActivity::class.java)
                .putExtra(DetailActivity.EXTRA_TITLE, getString(R.string.page_assistants_title))
                .putExtra(DetailActivity.EXTRA_PATH, "assistants"))
        }
        for (tile in summaryTiles) {
            val card = findViewById<View>(tile.id)
            card.findViewById<TextView>(R.id.summaryLabel).setText(tile.label)
            card.contentDescription = getString(tile.label) + ". " + getString(R.string.summary_waiting)
            card.setOnClickListener { openModule(tile.route) }
        }
        ViewCompat.setAccessibilityHeading(findViewById(R.id.summaryHeading), true)
        ViewCompat.setAccessibilityHeading(findViewById(R.id.attentionHeading), true)
        findViewById<View>(R.id.refreshSummary).setOnClickListener { loadSummary() }
        updateGrid(resources.configuration)
    }

    override fun onConfigurationChanged(newConfig: Configuration) {
        super.onConfigurationChanged(newConfig)
        updateGrid(newConfig)
    }

    private fun updateGrid(config: Configuration) {
        val columns = if (config.screenWidthDp < 360 || config.fontScale >= 1.3f) 1 else 2
        for (gridId in listOf(R.id.moduleGrid, R.id.summaryGrid)) {
            val grid = findViewById<GridLayout>(gridId)
            // Clear computed specs before changing the column count on rotation.
            for (index in 0 until grid.childCount) {
                val child = grid.getChildAt(index)
                child.layoutParams = (child.layoutParams as GridLayout.LayoutParams).apply {
                    columnSpec = GridLayout.spec(GridLayout.UNDEFINED, 1f)
                    rowSpec = GridLayout.spec(GridLayout.UNDEFINED)
                }
            }
            grid.columnCount = columns
            if (gridId == R.id.summaryGrid) {
                val last = grid.getChildAt(grid.childCount - 1)
                last.layoutParams = (last.layoutParams as GridLayout.LayoutParams).apply {
                    columnSpec = GridLayout.spec(GridLayout.UNDEFINED, columns, 1f)
                }
            }
        }
    }

    override fun onCreateOptionsMenu(menu: Menu): Boolean {
        menuInflater.inflate(R.menu.dashboard_menu, menu)
        return true
    }

    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        if (item.itemId == R.id.action_settings) {
            showServerSettingsDialog()
            return true
        }
        return super.onOptionsItemSelected(item)
    }

    private fun showServerSettingsDialog() {
        val settingsView = layoutInflater.inflate(R.layout.dialog_server_settings, null)
        val field = settingsView.findViewById<TextInputLayout>(R.id.serverHostField)
        val input = settingsView.findViewById<TextInputEditText>(R.id.serverHostInput)
        val summaryField = settingsView.findViewById<TextInputLayout>(R.id.summaryApiField)
        val summaryInput = settingsView.findViewById<TextInputEditText>(R.id.summaryApiInput)
        summaryInput.setText(prefs.getString(PREF_SUMMARY_API, ""))
        input.setText(prefs.getString(PREF_SERVER_HOST, getString(R.string.default_server_host)))
        val dialog = MaterialAlertDialogBuilder(this)
            .setTitle(R.string.settings)
            .setView(settingsView)
            .setPositiveButton(R.string.save, null)
            .setNegativeButton(R.string.cancel, null)
            .create()
        dialog.setOnShowListener {
            dialog.getButton(android.content.DialogInterface.BUTTON_POSITIVE).setOnClickListener {
                val host = input.text.toString().trim().ifEmpty { getString(R.string.default_server_host) }
                val normalized = if (host.contains("://")) host else "http://$host"
                val summary = summaryInput.text.toString().trim()
                val normalizedSummary = if (summary.isEmpty() || summary.contains("://")) summary else "http://$summary"
                field.error = null
                summaryField.error = null
                if (!validAddress(normalized)) {
                    field.error = getString(R.string.server_host_invalid)
                } else if (normalizedSummary.isNotEmpty() && !validAddress(normalizedSummary)) {
                    summaryField.error = getString(R.string.server_host_invalid)
                } else {
                    prefs.edit().putString(PREF_SERVER_HOST, normalized.trimEnd('/'))
                        .putString(PREF_SUMMARY_API, normalizedSummary.trimEnd('/')).apply()
                    loadSummary()
                    Toast.makeText(this, R.string.server_saved, Toast.LENGTH_SHORT).show()
                    dialog.dismiss()
                }
            }
        }
        dialog.show()
    }


    private fun validAddress(value: String): Boolean {
        val uri = Uri.parse(value)
        return uri.scheme in listOf("http", "https") && !uri.host.isNullOrBlank() && value.none { it.isWhitespace() }
    }

    private fun openModule(route: String) {
        val title = when (route) {
            "network" -> R.string.page_network_title
            "steering" -> R.string.page_steering_title
            "gis" -> R.string.page_gis_title
            "churn" -> R.string.page_churn_title
            else -> R.string.page_overview_title
        }
        startActivity(Intent(this, DetailActivity::class.java)
            .putExtra(DetailActivity.EXTRA_TITLE, getString(title))
            .putExtra(DetailActivity.EXTRA_PATH, route))
    }

    private fun summaryEndpoint(): String {
        val override = prefs.getString(PREF_SUMMARY_API, "").orEmpty()
        if (override.isNotBlank()) return override.trimEnd('/') + "/dashboard/summary"
        val host = prefs.getString(PREF_SERVER_HOST, getString(R.string.default_server_host))!!
        return Uri.parse(host).buildUpon().encodedAuthority(Uri.parse(host).host.let {
            if (it != null && it.contains(':')) "[$it]:8511" else "$it:8511"
        }).path("/dashboard/summary").clearQuery().fragment(null).build().toString()
    }

    private fun loadSummary() {
        val generation = ++summaryGeneration
        summaryConnection?.disconnect()
        summaryJob?.cancel(true)
        val endpoint = summaryEndpoint()
        findViewById<View>(R.id.summaryProgress).visibility = View.VISIBLE
        findViewById<View>(R.id.refreshSummary).isEnabled = false
        findViewById<TextView>(R.id.summaryStatus).setText(R.string.summary_loading)
        summaryJob = summaryExecutor.submit {
            var connection: HttpURLConnection? = null
            val result = runCatching {
                connection = URL(endpoint).openConnection() as HttpURLConnection
                summaryConnection = connection
                connection!!.connectTimeout = 4000
                connection!!.readTimeout = 35000
                connection!!.setRequestProperty("Accept", "application/json")
                check(connection!!.responseCode == 200)
                JSONObject(connection!!.inputStream.bufferedReader().use { it.readText() }).also {
                    check(it.getInt("schema_version") == 1)
                    val cards = it.getJSONArray("cards")
                    check(cards.length() == summaryTiles.size)
                    check((0 until cards.length()).map { index -> cards.getJSONObject(index).getString("id") }.toSet() == summaryTiles.map { tile -> tile.key }.toSet())
                }
            }
            connection?.disconnect()
            runOnUiThread {
                if (isDestroyed || generation != summaryGeneration) return@runOnUiThread
                lastSummaryFetch = System.currentTimeMillis()
                findViewById<View>(R.id.summaryProgress).visibility = View.GONE
                findViewById<View>(R.id.refreshSummary).isEnabled = true
                renderSummary(result.getOrNull())
            }
        }
    }

    private fun renderSummary(summary: JSONObject?) {
        val cards = summary?.optJSONArray("cards")
        for (tile in summaryTiles) {
            val data = (0 until (cards?.length() ?: 0)).map { cards!!.getJSONObject(it) }.find { it.optString("id") == tile.key }
            val available = data?.optBoolean("available") == true
            val value = if (available) data!!.optString("value") else getString(R.string.summary_dash)
            val note = if (available) data!!.optString("note") else getString(R.string.summary_unavailable)
            val card = findViewById<View>(tile.id)
            card.findViewById<TextView>(R.id.summaryValue).apply {
                text = value
                setTextColor(getColor(if (available) R.color.text_primary else R.color.text_secondary))
            }
            card.findViewById<TextView>(R.id.summaryNote).text = note
            card.contentDescription = "${getString(tile.label)}. $value. $note"
        }
        val available = summary?.optInt("available") ?: 0
        findViewById<TextView>(R.id.summaryStatus).text = if (summary == null) getString(R.string.summary_error) else {
            getString(R.string.summary_partial, available, summaryTiles.size, SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date()))
        }
        val notes = findViewById<LinearLayout>(R.id.attentionList)
        notes.removeAllViews()
        val items = summary?.optJSONArray("attention")
        for (index in 0 until (items?.length() ?: 0)) {
            val item = items!!.getJSONObject(index)
            val route = item.optString("route")
            if (route !in listOf("network", "steering", "gis", "churn")) continue
            val card = MaterialCardView(this).apply {
                radius = dp(16).toFloat()
                cardElevation = 0f
                setCardBackgroundColor(getColor(R.color.surface))
                strokeColor = getColor(R.color.outline)
                strokeWidth = dp(1)
                rippleColor = ColorStateList.valueOf(getColor(R.color.card_ripple))
                isClickable = true
                isFocusable = true
                contentDescription = item.optString("title") + ". " + item.optString("note")
                setOnClickListener { openModule(route) }
            }
            val body = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(dp(16), dp(14), dp(16), dp(14))
                importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS
                addView(TextView(context).apply {
                    text = item.optString("title")
                    textSize = 15f
                    setTypeface(typeface, Typeface.BOLD)
                    setTextColor(getColor(R.color.text_primary))
                })
                addView(TextView(context).apply {
                    text = item.optString("note")
                    textSize = 13f
                    setPadding(0, dp(6), 0, 0)
                    setTextColor(getColor(R.color.text_secondary))
                })
            }
            card.addView(body)
            notes.addView(card, LinearLayout.LayoutParams(-1, -2).apply { bottomMargin = dp(8) })
        }
        if (notes.childCount == 0) notes.addView(TextView(this).apply {
            setText(if (available == summaryTiles.size) R.string.summary_no_notes else R.string.summary_missing_notes)
            textSize = 14f
            setTextColor(getColor(R.color.text_secondary))
        })
    }

    private fun dp(value: Int) = (value * resources.displayMetrics.density).toInt()

    override fun onResume() {
        super.onResume()
        if (System.currentTimeMillis() - lastSummaryFetch > 30_000 && summaryJob?.isDone != false) loadSummary()
    }

    override fun onDestroy() {
        summaryGeneration++
        summaryConnection?.disconnect()
        summaryJob?.cancel(true)
        summaryExecutor.shutdownNow()
        super.onDestroy()
    }

    companion object {
        const val PREF_SERVER_HOST = "server_host"
        const val PREF_SUMMARY_API = "summary_api"
    }
}
