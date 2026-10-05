import unittest

import h3
import pandas as pd

from antenna_cell_placement.h3_grid import (
    generate_h3_cells_for_bbox,
    h3_cells_to_gdf,
    assign_points_to_h3,
    aggregate_existing_sites_per_hex,
)

TRIPOLI_BBOX = {"min_lat": 32.70, "max_lat": 33.05, "min_lon": 12.95, "max_lon": 13.45}
TRIPOLI_CENTER = (32.8872, 13.1913)  # (lat, lon)


class H3GridTests(unittest.TestCase):
    def test_generate_h3_cells_for_bbox_covers_known_point(self):
        cell_ids = generate_h3_cells_for_bbox(TRIPOLI_BBOX, resolution=8)
        expected_cell = h3.latlng_to_cell(TRIPOLI_CENTER[0], TRIPOLI_CENTER[1], 8)
        self.assertIn(expected_cell, cell_ids)
        self.assertGreater(len(cell_ids), 0)

    def test_assign_points_to_h3_is_deterministic(self):
        lons = [13.1913, 13.20, 13.05]
        lats = [32.8872, 32.90, 32.75]
        first = assign_points_to_h3(lons, lats, resolution=8)
        second = assign_points_to_h3(lons, lats, resolution=8)
        self.assertEqual(list(first), list(second))

    def test_h3_cells_to_gdf_centroids_within_bbox(self):
        cell_ids = generate_h3_cells_for_bbox(TRIPOLI_BBOX, resolution=8)
        grid_gdf = h3_cells_to_gdf(cell_ids)
        margin = 0.05  # hex overflow near the boundary is expected
        self.assertTrue((grid_gdf["centroid_lat"] >= TRIPOLI_BBOX["min_lat"] - margin).all())
        self.assertTrue((grid_gdf["centroid_lat"] <= TRIPOLI_BBOX["max_lat"] + margin).all())
        self.assertTrue((grid_gdf["centroid_lon"] >= TRIPOLI_BBOX["min_lon"] - margin).all())
        self.assertTrue((grid_gdf["centroid_lon"] <= TRIPOLI_BBOX["max_lon"] + margin).all())

    def test_aggregate_existing_sites_per_hex_conserves_site_count(self):
        cluster_a_cell = h3.latlng_to_cell(32.887, 13.191, 8)
        cluster_a_center = h3.cell_to_latlng(cluster_a_cell)
        cluster_b_cell = h3.latlng_to_cell(32.80, 13.30, 8)
        cluster_b_center = h3.cell_to_latlng(cluster_b_cell)

        df = pd.DataFrame({
            "physical_site_id": [1, 2, 3, 4, 5],
            "canonical_latitude": [
                cluster_a_center[0], cluster_a_center[0] + 0.0005, cluster_a_center[0] - 0.0005,
                cluster_b_center[0], cluster_b_center[0] + 0.0003,
            ],
            "canonical_longitude": [
                cluster_a_center[1], cluster_a_center[1] + 0.0005, cluster_a_center[1] - 0.0005,
                cluster_b_center[1], cluster_b_center[1] + 0.0003,
            ],
            "population_density_1km": [100.0, 200.0, 300.0, 50.0, 60.0],
            "population_sum_5km": [1000.0, 2000.0, 3000.0, 500.0, 600.0],
            "elevation_m": [10.0, 12.0, 8.0, 5.0, 6.0],
            "terrain_slope_deg": [1.0, 1.5, 0.5, 0.2, 0.3],
            "dist_to_nearest_road_m": [100.0, 150.0, 90.0, 300.0, 310.0],
            "dist_to_nearest_site_m": [50.0, 60.0, 40.0, 500.0, 510.0],
            "site_density_3km": [3, 3, 3, 1, 1],
            "has_libyana": [1, 0, 1, 1, 0],
            "has_almadar": [0, 1, 0, 0, 1],
        })

        agg = aggregate_existing_sites_per_hex(df, resolution=8)
        self.assertEqual(agg["site_count"].sum(), 5)
        self.assertEqual(len(agg), 2)
        cluster_a_row = agg[agg["h3_index"] == cluster_a_cell]
        self.assertEqual(cluster_a_row["site_count"].iloc[0], 3)
        cluster_b_row = agg[agg["h3_index"] == cluster_b_cell]
        self.assertEqual(cluster_b_row["site_count"].iloc[0], 2)


if __name__ == "__main__":
    unittest.main()
