import unittest

import h3
import numpy as np
import pandas as pd
from rasterio.transform import from_origin
from shapely.geometry import box

from antenna_cell_placement.h3_planning import (
    PARENT_H3_RESOLUTION,
    PRIMARY_H3_RESOLUTION,
    allocate_population_array,
    attach_h3_indexes,
    measure_h3_topology,
    summarize_candidate_units,
)


class H3PlanningTests(unittest.TestCase):
    def candidates(self):
        return pd.DataFrame(
            {
                "candidate_id": ["candidate-a", "candidate-b", "candidate-c"],
                "recommendation_rank": [1, 2, 3],
                "canonical_latitude": [32.8800, 32.8801, 31.2000],
                "canonical_longitude": [13.1800, 13.1801, 16.5900],
                "planning_priority_score": [90.0, 80.0, 70.0],
                "population_sum_5km": [1000.0, 900.0, 500.0],
            }
        )

    def test_h3_assignment_is_deterministic_hierarchical_and_non_mutating(self):
        candidates = self.candidates()
        original = candidates.copy(deep=True)
        first = attach_h3_indexes(candidates)
        second = attach_h3_indexes(candidates)

        pd.testing.assert_frame_equal(candidates, original)
        pd.testing.assert_frame_equal(first, second)
        pd.testing.assert_frame_equal(first[original.columns], original)
        self.assertTrue(first["h3_r7"].map(h3.is_valid_cell).all())
        self.assertTrue(
            all(
                h3.cell_to_parent(cell, PARENT_H3_RESOLUTION) == parent
                for cell, parent in zip(first["h3_r7"], first["h3_r6"])
            )
        )

    def test_parent_rollup_is_used_at_resolution_boundary(self):
        candidate = pd.DataFrame(
            {
                "canonical_latitude": [32.53345318780158],
                "canonical_longitude": [20.5852948396787],
            }
        )
        indexed = attach_h3_indexes(candidate)
        direct_r6 = h3.latlng_to_cell(
            candidate.loc[0, "canonical_latitude"],
            candidate.loc[0, "canonical_longitude"],
            PARENT_H3_RESOLUTION,
        )
        self.assertNotEqual(indexed.loc[0, "h3_r6"], direct_r6)
        self.assertEqual(
            indexed.loc[0, "h3_r6"],
            h3.cell_to_parent(indexed.loc[0, "h3_r7"], PARENT_H3_RESOLUTION),
        )

    def test_candidate_unit_summary_uses_stable_cells(self):
        summary = summarize_candidate_units(
            self.candidates(), PRIMARY_H3_RESOLUTION
        )
        self.assertEqual(summary["candidate_count"].sum(), 3)
        self.assertEqual(summary["candidate_count"].max(), 2)
        self.assertEqual(summary["maximum_priority_score"].max(), 90.0)

    def test_area_sampled_population_is_conserved(self):
        population = np.array([[1.0, 2.0], [3.0, 4.0]])
        transform = from_origin(0.0, 2.0, 1.0, 1.0)
        allocation, metrics = allocate_population_array(
            population,
            transform,
            box(0.0, 0.0, 2.0, 2.0),
            PRIMARY_H3_RESOLUTION,
            row_chunk_size=1,
            source_is_density=False,
        )
        self.assertAlmostEqual(sum(allocation.values()), 10.0)
        self.assertAlmostEqual(metrics["area_weighted_population"], 10.0)
        self.assertLess(metrics["population_conservation_error_pct"], 1e-9)
        self.assertEqual(metrics["inside_boundary_sample_count"], 16)
        self.assertEqual(metrics["assigned_sample_count"], 16)

    def test_boundary_pixels_receive_fractional_area_weight(self):
        population = np.array([[1.0, 2.0], [3.0, 4.0]])
        transform = from_origin(0.0, 2.0, 1.0, 1.0)
        allocation, metrics = allocate_population_array(
            population,
            transform,
            box(0.0, 0.0, 1.0, 2.0),
            PRIMARY_H3_RESOLUTION,
            source_is_density=False,
        )
        self.assertAlmostEqual(sum(allocation.values()), 4.0)
        self.assertEqual(metrics["inside_boundary_sample_count"], 8)
        self.assertEqual(metrics["assigned_sample_count"], 8)

    def test_exact_topology_has_no_internal_gaps_or_overlaps(self):
        metrics = measure_h3_topology(box(13.0, 32.0, 13.1, 32.1), resolution=7)
        self.assertTrue(metrics["coverage_topology_valid"])
        self.assertLess(metrics["boundary_gap_pct"], 1e-9)
        self.assertLess(metrics["boundary_overlap_pct"], 1e-9)
        self.assertGreater(metrics["boundary_leakage_before_clip_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
