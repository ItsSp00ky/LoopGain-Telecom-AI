import json
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
import requests
from mobile_summary import app, build_summary, fetch

def evidence():
    return {
        "kpi": {"breaches": 2, "checked": 60, "as_of": "2026-09-22"},
        "steering": {"latest_day": {"alerts_by_category": {"CRITICAL": 15}, "recommendations": 34}, "window_end": "2026-09-22"},
        "traffic": {"forecast": [{"date": "2026-09-23", "predicted_kpi_volume_gb": 2500000}]},
        "gis": {"features": [{"properties": {}}, {"properties": {}}]},
        "churn": {"subscribers": 100, "by_risk_band": [{"name": "high", "lyd_at_risk": 24000, "customers": 7}]},
    }

class SummaryTests(unittest.TestCase):
    def test_all_five_use_evidence_and_explicit_dates(self):
        result = build_summary(evidence())
        self.assertEqual(result["available"], 5)
        self.assertEqual([c["value"] for c in result["cards"]], ["2 / 60", "15", "2.50 PB", "2", "24k LYD"])
        self.assertEqual(result["cards"][2]["source_date"], "2026-09-23")
        self.assertNotIn("Next-day", json.dumps(result))
        self.assertIn("Backtest", result["cards"][1]["note"])

    def test_offline_never_becomes_zero(self):
        result = build_summary({})
        self.assertEqual(result["available"], 0)
        self.assertEqual(len(result["cards"]), 5)
        self.assertTrue(all(c["value"] == "—" and not c["available"] for c in result["cards"]))

    def test_bad_source_does_not_hide_other_metrics(self):
        sources = evidence()
        sources["traffic"]["forecast"] = []
        self.assertEqual(build_summary(sources)["available"], 4)

    def test_missing_risk_value_is_not_reported_as_zero(self):
        sources = evidence()
        sources["churn"]["by_risk_band"][0]["lyd_at_risk"] = None
        self.assertFalse(build_summary(sources)["cards"][4]["available"])

    def test_nonfinite_numbers_are_rejected(self):
        sources = evidence()
        sources["traffic"]["forecast"][0]["predicted_kpi_volume_gb"] = float("nan")
        self.assertFalse(build_summary(sources)["cards"][2]["available"])

    def test_transport_errors_are_redacted(self):
        with patch("mobile_summary.requests.get", side_effect=requests.ConnectionError("secret-key at internal-host")):
            self.assertIsNone(fetch("http://example.test", "/source"))

    def test_endpoint_skips_protected_churn_without_server_key(self):
        def config(name, default=""):
            return "" if name == "PREPAID_CHURN_COPILOT_KEY" else default
        with patch("mobile_summary.setting", side_effect=config), patch("mobile_summary.fetch", return_value=None) as mock:
            response = TestClient(app).get("/dashboard/summary")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock.call_count, 4)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.json()["available"], 0)

    def test_credentials_and_source_rows_are_never_returned(self):
        def config(name, default=""):
            return "server-only-test-key" if name == "PREPAID_CHURN_COPILOT_KEY" else default
        def source(base, path, headers, timeout):
            return evidence()[{"/kpis/status":"kpi", "/steering/summary":"steering", "/traffic/30day":"traffic", "/shortlist":"gis", "/portfolio/summary":"churn"}[path]]
        with patch("mobile_summary.setting", side_effect=config), patch("mobile_summary.fetch", side_effect=source):
            response = TestClient(app).get("/dashboard/summary")
        self.assertEqual(response.json()["available"], 5)
        self.assertNotIn("server-only-test-key", response.text)
        self.assertNotIn("by_risk_band", response.text)

if __name__ == "__main__":
    unittest.main()
