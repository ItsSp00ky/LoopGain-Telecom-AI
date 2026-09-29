import unittest

from fastapi.testclient import TestClient

from api import ALERTS_CSV, FORECAST_CSV, METRICS_CSV, TOWER_PREDICTIONS_CSV, app, kpi_config

HAS_KPI_RUN = METRICS_CSV.exists() and FORECAST_CSV.exists()


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_reports_raw_data_status(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_traffic_forecast_runs_the_real_pipeline(self):
        response = self.client.get("/traffic/30day")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn(body["champion_model"], {"Random Forest", "XGBoost Regressor", "Ridge Regression", "Seasonal Naive (t-7)"})
        self.assertEqual(len(body["forecast"]), 30)
        self.assertIn("WAPE (%)", body["test_metrics"])
        self.assertGreater(body["test_metrics"]["WAPE (%)"], 0)

    def test_rejects_unsupported_horizon(self):
        response = self.client.get("/traffic/999day")
        self.assertEqual(response.status_code, 422)


class KpiApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_catalog_lists_every_kpi_and_band(self):
        body = self.client.get("/kpis/catalog").json()
        self.assertEqual({k["key"] for k in body["kpis"]}, set(kpi_config.KPI_KEYS))
        self.assertEqual([b["band"] for b in body["bands"]], kpi_config.CARRIER_BANDS)

    def test_status_checks_every_kpi_on_every_band_against_its_sla(self):
        body = self.client.get("/kpis/status").json()
        self.assertEqual(body["checked"], len(kpi_config.KPI_KEYS) * len(kpi_config.CARRIER_BANDS))
        self.assertEqual(body["breaches"], sum(1 for row in body["status"] if row["sla_met"] is False))

    def test_downtime_sla_is_judged_per_cell_not_per_cluster(self):
        rows = self.client.get("/kpis/status").json()["status"]
        downtime = next(r for r in rows if r["kpi"] == "downtime_sec" and r["value"])
        cells = kpi_config.CARRIER_CLUSTER_CELLS[downtime["band"]]
        self.assertAlmostEqual(downtime["sla_value"], downtime["value"] / cells)

    @unittest.skipUnless(HAS_KPI_RUN, "no cellular_kpi_forecast run in this checkout")
    def test_scorecard_flags_forecasts_that_do_not_beat_naive(self):
        body = self.client.get("/kpis/scorecard").json()
        self.assertEqual(body["series"], len(body["scorecard"]))
        for row in body["scorecard"]:
            self.assertEqual(row["beats_naive"], row["test_mase"] < 1)

    @unittest.skipUnless(HAS_KPI_RUN, "no cellular_kpi_forecast run in this checkout")
    def test_forecast_carries_history_and_its_own_trust_flag(self):
        body = self.client.get("/kpis/forecast/1700/availability_pct", params={"days": 14}).json()
        self.assertEqual(len(body["forecast"]), 14)
        self.assertGreater(len(body["history"]), 0)
        self.assertEqual(body["beats_naive"], body["test_mase"] < 1)

    def test_unknown_band_or_kpi_is_404(self):
        self.assertEqual(self.client.get("/kpis/forecast/999/availability_pct").status_code, 404)
        self.assertEqual(self.client.get("/kpis/forecast/1700/not_a_kpi").status_code, 404)


@unittest.skipUnless(ALERTS_CSV.exists() and TOWER_PREDICTIONS_CSV.exists(), "no steering/tower outputs")
class SteeringApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_summary_counts_match_the_committed_outputs(self):
        body = self.client.get("/steering/summary").json()
        self.assertLessEqual(body["window_start"], body["window_end"])
        self.assertEqual(set(body["alerts_by_category"]), {"HIGH", "CRITICAL"})
        self.assertGreater(sum(body["recommendations_by_priority"].values()), 0)

    def test_recommendations_default_to_the_latest_day_and_filter(self):
        latest = self.client.get("/steering/summary").json()["window_end"]
        body = self.client.get("/steering/recommendations", params={"priority": "LOW", "limit": 5}).json()
        self.assertEqual(body["date"], latest)
        self.assertLessEqual(body["count"], 5)
        self.assertTrue(all(r["Priority"] == "LOW" for r in body["recommendations"]))
        risks = [r["Risk_Score"] for r in body["recommendations"]]
        self.assertEqual(risks, sorted(risks, reverse=True))

    def test_tower_forecast_pairs_actual_and_predicted_per_kpi(self):
        body = self.client.get("/towers/TWR_0001/forecast").json()
        self.assertEqual(set(body["series"]), {"connected_users", "dl_throughput_mbps", "availability_pct", "erab_drop_rate"})
        point = body["series"]["connected_users"][0]
        self.assertEqual(set(point), {"date", "actual", "predicted"})

    def test_unknown_tower_is_404(self):
        self.assertEqual(self.client.get("/towers/TWR_9999/forecast").status_code, 404)


if __name__ == "__main__":
    unittest.main()
