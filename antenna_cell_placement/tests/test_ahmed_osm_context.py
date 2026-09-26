import unittest

import geopandas as gpd
import h3
import pandas as pd
from shapely.geometry import Point, box

from antenna_cell_placement.osm_context import (
    ACTIVE_FAMILIES,
    OSMContextExtractor,
)


class OSMContextTests(unittest.TestCase):
    def features(self):
        rows = []
        geometries = []
        for index, family in enumerate(ACTIVE_FAMILIES):
            rows.append({"osm_id": str(index), "family": family, "name": family})
            geometries.append(Point(13.18 + index, 32.88))
        return gpd.GeoDataFrame(rows, geometry=geometries, crs="EPSG:4326")

    def test_context_is_deterministic_non_mutating_and_does_not_change_rank(self):
        cell = h3.latlng_to_cell(32.88, 13.18, 7)
        candidates = pd.DataFrame(
            {
                "candidate_id": ["candidate-a"],
                "recommendation_rank": [1],
                "planning_priority_score": [75.0],
                "h3_r7": [cell],
                "canonical_latitude": [32.88],
                "canonical_longitude": [13.18],
            }
        )
        original = candidates.copy(deep=True)
        extractor = OSMContextExtractor(self.features())
        first = extractor.add_context(candidates)
        second = extractor.add_context(candidates)

        pd.testing.assert_frame_equal(candidates, original)
        pd.testing.assert_frame_equal(first, second)
        pd.testing.assert_frame_equal(first[original.columns], original)
        self.assertEqual(first.loc[0, "osm_hospital_count_h3"], 1)
        self.assertAlmostEqual(first.loc[0, "osm_hospital_nearest_distance_m"], 0.0)
        self.assertTrue(first.loc[0, "osm_selected_context_available"])

    def test_polygon_uses_representative_point_and_absence_is_observation_only(self):
        features = self.features()
        features.loc[features["family"] == "industrial", "geometry"] = box(
            13.1799, 32.8799, 13.1801, 32.8801
        )
        candidate = pd.DataFrame(
            {
                "h3_r7": [h3.latlng_to_cell(32.88, 13.18, 7)],
                "canonical_latitude": [32.88],
                "canonical_longitude": [13.18],
            }
        )
        result = OSMContextExtractor(features).add_context(candidate)

        self.assertEqual(result.loc[0, "osm_industrial_count_h3"], 1)
        self.assertEqual(result.loc[0, "osm_aviation_count_h3"], 0)
        self.assertFalse(result.loc[0, "osm_aviation_observed_h3"])
        self.assertTrue(result.loc[0, "osm_selected_context_available"])

    def test_missing_required_candidate_fields_is_rejected(self):
        with self.assertRaises(KeyError):
            OSMContextExtractor(self.features()).add_context(pd.DataFrame({"h3_r7": []}))


if __name__ == "__main__":
    unittest.main()
