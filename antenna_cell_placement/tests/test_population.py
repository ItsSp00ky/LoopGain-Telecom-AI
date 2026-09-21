import unittest

import numpy as np
from rasterio.transform import from_origin

from antenna_cell_placement.population import (
    circular_population_sum,
    density_to_population_counts,
    pixel_areas_km2_by_row,
)


class PopulationTests(unittest.TestCase):
    def test_density_is_scaled_by_geodesic_pixel_area(self):
        transform = from_origin(10.0, 1.0, 0.01, 0.01)
        density = np.full((2, 2), 100.0)
        areas = pixel_areas_km2_by_row(transform, 2)
        counts = density_to_population_counts(density, transform)
        np.testing.assert_allclose(counts[:, 0], areas * 100.0)
        self.assertTrue(np.all((areas > 1.2) & (areas < 1.24)))

    def test_circular_catchment_excludes_square_corners(self):
        transform = from_origin(10.0, 0.03, 0.01, 0.01)
        counts = np.ones((3, 3), dtype=float)
        total = circular_population_sum(
            counts,
            transform,
            longitude=10.015,
            latitude=0.015,
            row=1,
            column=1,
            radius_m=1200.0,
        )
        self.assertEqual(total, 5.0)


if __name__ == "__main__":
    unittest.main()
