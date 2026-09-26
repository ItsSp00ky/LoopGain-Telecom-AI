import unittest

import numpy as np
import pandas as pd

from antenna_cell_placement.validation import (
    recompute_network_features,
    known_site_recovery,
    weight_sensitivity,
)


def synthetic_hexes(n=60, seed=0):
    rng = np.random.default_rng(seed)
    x = np.arange(n) * 1000.0
    return pd.DataFrame({
        "h3_index": [f"hex{i}" for i in range(n)],
        "utm_x": x,
        "utm_y": np.zeros(n),
        "population_sum_5km": rng.uniform(0, 10000, n),
        "dist_to_nearest_road_m": rng.uniform(0, 500, n),
        "dist_to_nearest_site_m": 0.0,
        "site_density_3km": 0,
        "existing_sites_site_count": 0,
    })


def synthetic_sites(df_hex, seed=1):
    # Sites concentrate in the most populated hexes, like a real network.
    rng = np.random.default_rng(seed)
    top = df_hex.sort_values("population_sum_5km", ascending=False).head(25)
    rows = []
    for _, hex_row in top.iterrows():
        for _ in range(rng.integers(1, 3)):
            rows.append({
                "utm_x": hex_row["utm_x"] + rng.uniform(-200, 200),
                "utm_y": rng.uniform(-200, 200),
                "h3_index": hex_row["h3_index"],
            })
    return pd.DataFrame(rows)


class ValidationTests(unittest.TestCase):
    def test_recompute_network_features(self):
        df_hex = synthetic_hexes(n=5)
        sites = pd.DataFrame({"utm_x": [0.0, 4000.0], "utm_y": [0.0, 0.0], "h3_index": ["hex0", "hex4"]})
        out = recompute_network_features(df_hex, sites)
        self.assertEqual(out.loc[0, "dist_to_nearest_site_m"], 0.0)
        self.assertEqual(out.loc[2, "dist_to_nearest_site_m"], 2000.0)
        self.assertEqual(out["existing_sites_site_count"].tolist(), [1, 0, 0, 0, 1])
        self.assertEqual(out.loc[0, "site_density_3km"], 1)  # hex4's site is 4km away
        self.assertEqual(out.loc[2, "site_density_3km"], 2)  # both sites within 2km

    def test_recompute_with_no_sites(self):
        out = recompute_network_features(synthetic_hexes(n=3), pd.DataFrame(columns=["utm_x", "utm_y", "h3_index"]))
        self.assertTrue((out["existing_sites_site_count"] == 0).all())
        self.assertTrue((out["dist_to_nearest_site_m"] > 0).all())

    def test_known_site_recovery_reports_metrics(self):
        df_hex = synthetic_hexes()
        sites = synthetic_sites(df_hex)
        report = known_site_recovery(df_hex, sites, n_folds=3, hide_fraction=0.3)
        self.assertEqual(report["n_folds"], 3)
        self.assertTrue(0.0 <= report["mean_auc_expansion_score"] <= 1.0)
        self.assertTrue(0.0 <= report["mean_recall_top10pct_expansion_score"] <= 1.0)
        self.assertEqual(len(report["folds"]), 3)

    def test_weight_sensitivity_returns_correlations(self):
        results = weight_sensitivity(synthetic_hexes(), top_n=10)
        self.assertGreater(len(results), 0)
        for row in results:
            self.assertTrue(-1.0 <= row["spearman_rank_correlation"] <= 1.0)
            self.assertTrue(0.0 <= row["top10_overlap"] <= 1.0)


if __name__ == "__main__":
    unittest.main()
