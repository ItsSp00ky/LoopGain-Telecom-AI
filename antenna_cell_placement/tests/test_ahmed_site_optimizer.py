import unittest

import numpy as np
import pandas as pd

from antenna_cell_placement.planning_score import (
    SCORE_VERSION,
    add_reason_codes,
    candidate_id,
    eligible_candidate_mask,
    score_candidate_features,
)


class SiteOptimizerTests(unittest.TestCase):
    def candidates(self):
        return pd.DataFrame(
            {
                "inside_libya": [True, True, False, True],
                "population_data_available": [True, True, True, True],
                "terrain_data_available": [True, True, True, False],
                "worldcover_data_available": [True, True, True, True],
                "worldcover_is_water": [False, False, False, False],
                "population_sum_5km": [10_000.0, 10_000.0, 10_000.0, 10_000.0],
                "dist_to_nearest_site_m": [10_000.0, 2_999.0, 10_000.0, 10_000.0],
                "dist_to_nearest_road_m": [500.0, 500.0, 500.0, 500.0],
                "elevation_m": [100.0, 100.0, 100.0, np.nan],
                "elevation_prominence_3km": [20.0, 20.0, 20.0, np.nan],
                "terrain_slope_deg": [3.0, 3.0, 3.0, np.nan],
            }
        )

    def test_filters_are_strict_and_do_not_fill_top_k(self):
        mask = eligible_candidate_mask(self.candidates())
        self.assertEqual(mask.tolist(), [True, False, False, False])

    def test_confirmed_water_is_not_eligible(self):
        candidates = self.candidates()
        candidates.loc[0, "worldcover_is_water"] = True
        self.assertFalse(eligible_candidate_mask(candidates).iloc[0])
        self.assertTrue(
            eligible_candidate_mask(candidates, require_worldcover=False).iloc[0]
        )

    def test_score_is_deterministic_auditable_and_missing_stays_missing(self):
        first = score_candidate_features(self.candidates())
        second = score_candidate_features(self.candidates())
        pd.testing.assert_frame_equal(first, second)
        self.assertEqual(first.loc[0, "score_version"], SCORE_VERSION)
        self.assertGreater(first.loc[0, "planning_priority_score"], 0)
        self.assertTrue(pd.isna(first.loc[3, "planning_priority_score"]))

    def test_candidate_id_is_stable_and_source_sensitive(self):
        row = pd.Series(
            {
                "canonical_latitude": 32.1234567,
                "canonical_longitude": 13.7654321,
                "candidate_source": "road_sample",
            }
        )
        self.assertEqual(candidate_id(row), candidate_id(row.copy()))
        row["candidate_source"] = "settlement_ring"
        self.assertNotEqual(
            candidate_id(row),
            candidate_id(pd.Series({
                "canonical_latitude": 32.1234567,
                "canonical_longitude": 13.7654321,
                "candidate_source": "road_sample",
            })),
        )

    def test_empty_reason_codes_are_well_formed(self):
        empty = add_reason_codes(self.candidates().iloc[:0])
        self.assertIn("reason_codes", empty.columns)
        self.assertTrue(empty.empty)


if __name__ == "__main__":
    unittest.main()
