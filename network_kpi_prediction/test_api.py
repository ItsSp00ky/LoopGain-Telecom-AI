import unittest

from fastapi.testclient import TestClient

from api import app


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


if __name__ == "__main__":
    unittest.main()
