"""WorldPop density conversion and catchment aggregation helpers."""

import numpy as np
from pyproj import Geod
from rasterio.transform import Affine


WGS84_GEOD = Geod(ellps="WGS84")
WORLDPOP_SOURCE_UNIT = "people_per_km2"


def pixel_areas_km2_by_row(transform: Affine, height: int) -> np.ndarray:
    """Return ellipsoidal area for one geographic raster pixel in each row."""
    if transform.b != 0 or transform.d != 0:
        raise ValueError("Rotated population rasters are not supported")
    if transform.a <= 0 or transform.e >= 0:
        raise ValueError("Population raster must be north-up with positive x scale")

    west = transform.c
    east = west + transform.a
    areas = np.empty(height, dtype=np.float64)
    for row in range(height):
        north = transform.f + row * transform.e
        south = north + transform.e
        area_m2, _ = WGS84_GEOD.polygon_area_perimeter(
            [west, east, east, west],
            [north, north, south, south],
        )
        areas[row] = abs(area_m2) / 1_000_000.0
    return areas
