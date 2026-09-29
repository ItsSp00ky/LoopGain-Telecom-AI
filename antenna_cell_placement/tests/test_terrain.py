"""Terrain unit and missing-data regression checks."""

import math
import unittest

import numpy as np
from rasterio.transform import from_origin

from antenna_cell_placement.terrain import TerrainSampler


class TerrainSamplerTests(unittest.TestCase):
    def test_slope_is_invariant_to_pixel_spacing(self):
        slopes = []
        for spacing in (0.002, 0.001):
            transform = from_origin(10.0, 33.0, spacing, spacing)
            rows, cols = np.indices((201, 201))
            # Approximately a 1% eastward grade at this latitude.
            metres_per_column = spacing * 93_000
            array = cols.astype(np.float32) * metres_per_column * 0.01
            sampler = TerrainSampler(array, transform)
            lon, lat = transform @ (100.5, 100.5)
            sample = sampler.sample(lon, lat)
            self.assertTrue(sample["terrain_data_available"])
            self.assertAlmostEqual(sample["terrain_slope_deg"], math.degrees(math.atan(0.01)), delta=0.03)
            self.assertAlmostEqual(sample["elevation_prominence_3km"], 0.0, delta=0.1)
            slopes.append(sample["terrain_slope_deg"])
        self.assertAlmostEqual(slopes[0], slopes[1], delta=0.01)

    def test_nodata_and_incomplete_tile_remain_unavailable(self):
        transform = from_origin(10.0, 33.0, 0.001, 0.001)
        array = np.full((100, 100), 100.0, dtype=np.float32)
        sampler = TerrainSampler(array, transform)
        lon, lat = transform @ (1.5, 1.5)
        self.assertFalse(sampler.sample(lon, lat, require_full_window=True)["terrain_data_available"])
        array[50, 50] = np.nan
        sampler = TerrainSampler(array, transform)
        lon, lat = transform @ (50.5, 50.5)
        self.assertFalse(sampler.sample(lon, lat)["terrain_data_available"])


if __name__ == "__main__":
    unittest.main()
