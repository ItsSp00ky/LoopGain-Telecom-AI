import unittest

import pandas as pd

from antenna_cell_placement.expansion_score import (
    DEFAULT_WEIGHTS,
    _minmax_normalize,
    compute_expansion_need_score,
)


class ExpansionScoreTests(unittest.TestCase):
    def test_minmax_normalize_handles_constant_column(self):
        series = pd.Series([5.0, 5.0, 5.0])
        result = _minmax_normalize(series)
        self.assertTrue((result == 0.5).all())

    def test_weights_sum_invariant(self):
        self.assertAlmostEqual(sum(DEFAULT_WEIGHTS.values()), 1.0, places=6)

    def test_known_high_site_density_hex_scores_low_network_gap(self):
        df = pd.DataFrame({
            "h3_index": ["dense", "sparse"],
            "population_sum_5km": [5000.0, 5000.0],
            "dist_to_nearest_site_m": [200.0, 8000.0],
            "site_density_3km": [15, 0],
        })
        scored = compute_expansion_need_score(df)
        dense_gap = scored.loc[scored["h3_index"] == "dense", "network_gap_score"].iloc[0]
        sparse_gap = scored.loc[scored["h3_index"] == "sparse", "network_gap_score"].iloc[0]
        self.assertLess(dense_gap, sparse_gap)

    def test_underserved_populated_hex_scores_higher_than_saturated_hex(self):
        df = pd.DataFrame({
            "h3_index": ["underserved", "saturated"],
            "population_sum_5km": [8000.0, 8000.0],
            "dist_to_nearest_site_m": [9000.0, 100.0],
            "site_density_3km": [0, 20],
            "existing_sites_site_count": [0, 5],
        })
        scored = compute_expansion_need_score(df)
        underserved_score = scored.loc[scored["h3_index"] == "underserved", "expansion_need_score"].iloc[0]
        saturated_score = scored.loc[scored["h3_index"] == "saturated", "expansion_need_score"].iloc[0]
        self.assertGreater(underserved_score, saturated_score)

    def test_missing_phase2_columns_degrades_gracefully(self):
        df = pd.DataFrame({
            "h3_index": ["a", "b"],
            "population_sum_5km": [1000.0, 5000.0],
            "dist_to_nearest_site_m": [500.0, 6000.0],
            "site_density_3km": [5, 0],
        })
        scored = compute_expansion_need_score(df)
        self.assertIn("expansion_need_score", scored.columns)
        self.assertFalse(scored["expansion_need_score"].isna().any())


if __name__ == "__main__":
    unittest.main()
