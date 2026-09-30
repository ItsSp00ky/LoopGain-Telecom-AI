package com.loopgain.kpimonitor

import android.app.AlertDialog
import android.content.Intent
import android.os.Bundle
import android.view.Menu
import android.view.MenuItem
import android.view.View
import android.widget.EditText
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

    private data class ModulePage(val title: String, val subtitle: String, val urlPath: String, val colorRes: Int)

    private val prefs by lazy { getSharedPreferences("kpi_monitor", MODE_PRIVATE) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_dashboard)
        setSupportActionBar(findViewById<Toolbar>(R.id.toolbar))

        val pages = listOf(
            ModulePage(getString(R.string.page_overview_title), getString(R.string.page_overview_subtitle), "", R.color.card_overview) to R.id.cardOverview,
            ModulePage(getString(R.string.page_network_title), getString(R.string.page_network_subtitle), "network", R.color.card_network) to R.id.cardNetwork,
            ModulePage(getString(R.string.page_steering_title), getString(R.string.page_steering_subtitle), "steering", R.color.card_steering) to R.id.cardSteering,
            ModulePage(getString(R.string.page_gis_title), getString(R.string.page_gis_subtitle), "gis", R.color.card_gis) to R.id.cardGis,
            ModulePage(getString(R.string.page_churn_title), getString(R.string.page_churn_subtitle), "churn", R.color.card_churn) to R.id.cardChurn,
            ModulePage(getString(R.string.page_assistants_title), getString(R.string.page_assistants_subtitle), "assistants", R.color.card_assistants) to R.id.cardAssistants,
        )

        for ((page, cardId) in pages) {
            val card = findViewById<View>(cardId)
            card.findViewById<TextView>(R.id.cardTitle).text = page.title
            card.findViewById<TextView>(R.id.cardSubtitle).text = page.subtitle
            card.findViewById<View>(R.id.cardAccent).setBackgroundColor(getColor(page.colorRes))
            card.setOnClickListener {
                startActivity(
                    Intent(this, DetailActivity::class.java)
                        .putExtra(DetailActivity.EXTRA_TITLE, page.title)
                        .putExtra(DetailActivity.EXTRA_PATH, page.urlPath)
                )
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
        val input = EditText(this).apply {
            hint = getString(R.string.server_host_hint)
            setText(prefs.getString(PREF_SERVER_HOST, getString(R.string.default_server_host)))
        }
        AlertDialog.Builder(this)
            .setTitle(R.string.server_host_label)
            .setView(input)
            .setPositiveButton(R.string.save) { _, _ ->
                val host = input.text.toString().trim().ifEmpty { getString(R.string.default_server_host) }
                val normalized = if (host.startsWith("http")) host else "http://$host"
                prefs.edit().putString(PREF_SERVER_HOST, normalized.trimEnd('/')).apply()
            }
            .setNegativeButton(R.string.cancel, null)
            .show()
    }

    companion object {
        const val PREF_SERVER_HOST = "server_host"
    }
}
