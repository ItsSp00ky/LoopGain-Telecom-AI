import unittest

import numpy as np
import pandas as pd

from antenna_cell_placement.evaluation import (
    binary_metrics,
    offset_points,
    select_test_municipalities,
)
from antenna_cell_placement.placement_model import label_equipment_tiers


def legacy_tier(row):
    pop_1km = row["population_density_1km"]
    if row["primary_tower_type"] == "MICRO" or (pop_1km > 2500 and row["dist_to_nearest_site_m"] < 250):
        return "Micro_Cell_Hotspot"
    if pop_1km >= 1200 or row["total_bandwidth_mhz"] >= 40.0 or row["total_carrier_count"] >= 3:
        return "Urban_HighCapacity_Macro"
    if pop_1km >= 150 or row["total_bandwidth_mhz"] >= 20.0 or row["dist_to_nearest_road_m"] < 500:
        return "Suburban_Standard_Macro"
    return "Rural_Coverage_Macro"


class EvaluationTests(unittest.TestCase):
    def test_label_equipment_tiers_matches_original_loop(self):
        rng = np.random.default_rng(0)
        n = 400
        df = pd.DataFrame({
            "population_density_1km": rng.choice([0, 10, 149, 150, 1199, 1200, 2600, 5000], n),
            "total_bandwidth_mhz": rng.choice([0.0, 10.0, 19.9, 20.0, 39.9, 40.0], n),
            "total_carrier_count": rng.choice([0, 1, 2, 3, 4], n),
            "primary_tower_type": rng.choice(["MACRO", "MICRO"], n, p=[0.9, 0.1]),
            "dist_to_nearest_site_m": rng.choice([50.0, 249.0, 250.0, 900.0, 8000.0], n),
            "dist_to_nearest_road_m": rng.choice([10.0, 499.0, 500.0, 4000.0], n),
        })
        expected = df.apply(legacy_tier, axis=1)
        self.assertEqual(label_equipment_tiers(df).tolist(), expected.tolist())
        self.assertEqual(len(set(expected)), 4)

    def test_select_test_municipalities_is_deterministic_and_bounded(self):
        counts = {"A": 400, "B": 250, "C": 120, "D": 80, "E": 60, "F": 40, "G": 30, "H": 20}
        series = pd.Series([name for name, k in counts.items() for _ in range(k)])
        first = select_test_municipalities(series, share=0.2, max_share=0.3, seed=1)
        second = select_test_municipalities(series, share=0.2, max_share=0.3, seed=1)
        self.assertEqual(first, second)
        covered = sum(counts[name] for name in first)
        self.assertGreater(covered, 0)
        self.assertLessEqual(covered, 0.3 * len(series))
        self.assertTrue(set(first) <= set(counts))

    def test_offset_points_moves_the_requested_distance(self):
        lons, lats = np.array([13.19, 20.07]), np.array([32.88, 32.12])
        distances = np.array([1000.0, 2500.0])
        new_lons, new_lats = offset_points(lons, lats, distances, np.array([0.7, 3.9]))
        dx = (new_lons - lons) * 111_320.0 * np.cos(np.radians(lats))
        dy = (new_lats - lats) * 111_320.0
        np.testing.assert_allclose(np.hypot(dx, dy), distances, rtol=1e-6)

    def test_binary_metrics_perfect_and_random(self):
        y = np.array([0, 0, 1, 1])
        perfect = binary_metrics(y, np.array([0.1, 0.2, 0.8, 0.9]))
        self.assertEqual(perfect["roc_auc"], 1.0)
        self.assertEqual(perfect["accuracy"], 1.0)
        self.assertEqual(perfect["n_positive"], 2)
        inverted = binary_metrics(y, np.array([0.9, 0.8, 0.2, 0.1]))
        self.assertEqual(inverted["roc_auc"], 0.0)


if __name__ == "__main__":
    unittest.main()
