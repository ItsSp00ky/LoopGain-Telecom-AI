import tempfile
import unittest
from pathlib import Path

import pandas as pd

from antenna_cell_placement.cloudflare_radar import (
    CLOUDFLARE_TO_OCHA_MUNICIPALITY,
    add_regional_features,
    load_regional_features,
)


class CloudflareRadarTests(unittest.TestCase):
    def fixture(self, directory: str) -> Path:
        path = Path(directory) / "radar.csv"
        pd.DataFrame(
            {
                "place_name": ["Tripoli", "Banghazi"],
                "http_requests_share_52w_pct": [75.0, 25.0],
                "digital_connectivity_index": [80.0, 20.0],
                "annual_stability_score_52w": [0.9, 0.8],
                "annual_traffic_growth_52w_pct": [3.0, -2.0],
            }
        ).to_csv(path, index=False)
        return path

    def test_all_22_places_have_explicit_admin_mapping(self):
        radar = load_regional_features()
        self.assertEqual(len(radar), 22)
        self.assertEqual(len(CLOUDFLARE_TO_OCHA_MUNICIPALITY), 22)
        self.assertFalse(radar["municipality_name"].isna().any())

    def test_join_and_bounded_priority_factor(self):
        with tempfile.TemporaryDirectory() as directory:
            enriched = add_regional_features(
                pd.DataFrame({"municipality_name": ["Tripoli", "Benghazi"]}),
                self.fixture(directory),
            )
        self.assertEqual(enriched["cloudflare_data_available"].tolist(), [True, True])
        self.assertGreater(
            enriched.loc[0, "cloudflare_regional_demand_score"],
            enriched.loc[1, "cloudflare_regional_demand_score"],
        )
        self.assertTrue(enriched["cloudflare_priority_factor"].between(0.9, 1.1).all())

    def test_missing_file_is_neutral(self):
        result = add_regional_features(
            pd.DataFrame({"municipality_name": ["Tripoli"]}),
            Path("/tmp/does-not-exist-cloudflare-radar.csv"),
        )
        self.assertFalse(result.loc[0, "cloudflare_data_available"])
        self.assertEqual(result.loc[0, "cloudflare_priority_factor"], 1.0)

    def test_unknown_municipality_is_neutral(self):
        with tempfile.TemporaryDirectory() as directory:
            result = add_regional_features(
                pd.DataFrame({"municipality_name": ["Unknown"]}),
                self.fixture(directory),
            )
        self.assertFalse(result.loc[0, "cloudflare_data_available"])
        self.assertEqual(result.loc[0, "cloudflare_priority_factor"], 1.0)

    def test_join_preserves_the_callers_index(self):
        frame = pd.DataFrame({"municipality_name": ["Tripoli", "Unknown"]}, index=[8, 2])
        with tempfile.TemporaryDirectory() as directory:
            result = add_regional_features(frame, self.fixture(directory))
        pd.testing.assert_index_equal(result.index, frame.index)

    def test_non_finite_demand_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.fixture(directory)
            frame = pd.read_csv(path)
            frame.loc[0, "http_requests_share_52w_pct"] = float("inf")
            frame.to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, "non-finite"):
                load_regional_features(path)


if __name__ == "__main__":
    unittest.main()
