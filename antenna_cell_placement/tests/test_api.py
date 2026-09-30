import unittest

from fastapi.testclient import TestClient

from antenna_cell_placement.api import DEFAULT_RUN_DIR, FULL_MAP, app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_reports_source_status(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn(body["status"], {"ok", "degraded"})
        self.assertIn("sources", body)

    def test_assess_returns_the_same_shape_as_the_cli(self):
        response = self.client.get("/assess", params={"lat": 32.8, "lon": 13.2})
        if response.status_code == 503:
            self.skipTest("required source data is not verified in this checkout")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("planning_priority_score", body)

    def test_assess_rejects_unknown_operator(self):
        response = self.client.get("/assess", params={"lat": 32.8, "lon": 13.2, "operator": "orange"})
        self.assertEqual(response.status_code, 422)

    @unittest.skipUnless((DEFAULT_RUN_DIR / "manifest.json").exists(), "no completed run in this checkout")
    def test_shortlist_serves_the_completed_run(self):
        response = self.client.get("/shortlist")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body.get("type"), "FeatureCollection")

    def test_full_map_is_served_when_built(self):
        response = self.client.get("/full-map")
        if FULL_MAP.exists():
            self.assertEqual(response.status_code, 200)
            self.assertIn("Existing sites: Libyana", response.text)
        else:
            self.assertEqual(response.status_code, 404)

    def test_shortlist_404s_on_a_missing_run(self):
        response = self.client.get("/shortlist", params={"run_dir": "no/such/run"})
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
