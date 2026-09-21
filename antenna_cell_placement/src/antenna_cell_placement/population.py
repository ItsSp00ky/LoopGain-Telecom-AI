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


def density_to_population_counts(
    density: np.ndarray,
    transform: Affine,
) -> np.ndarray:
    """Convert a people/km² raster to estimated people per source pixel."""
    values = np.asarray(density, dtype=np.float64)
    if values.ndim != 2:
        raise ValueError("Population density raster must be two-dimensional")
    areas = pixel_areas_km2_by_row(transform, values.shape[0])
    return values * areas[:, np.newaxis]


def circular_population_sum(
    population_counts: np.ndarray,
    transform: Affine,
    longitude: float,
    latitude: float,
    row: int,
    column: int,
    radius_m: float = 5000.0,
) -> float:
    """Sum population pixels whose centers fall within a geodesic radius."""
    latitude_pixel_m = abs(transform.e) * 111_320.0
    longitude_pixel_m = max(
        abs(transform.a) * 111_320.0 * np.cos(np.radians(latitude)),
        1.0,
    )
    row_radius = int(np.ceil(radius_m / latitude_pixel_m)) + 1
    column_radius = int(np.ceil(radius_m / longitude_pixel_m)) + 1
    row_start = max(0, row - row_radius)
    row_stop = min(population_counts.shape[0], row + row_radius + 1)
    column_start = max(0, column - column_radius)
    column_stop = min(population_counts.shape[1], column + column_radius + 1)

    rows, columns = np.meshgrid(
        np.arange(row_start, row_stop),
        np.arange(column_start, column_stop),
        indexing="ij",
    )
    pixel_lons = (
        transform.c
        + (columns + 0.5) * transform.a
        + (rows + 0.5) * transform.b
    )
    pixel_lats = (
        transform.f
        + (columns + 0.5) * transform.d
        + (rows + 0.5) * transform.e
    )
    _, _, distances = WGS84_GEOD.inv(
        np.full(pixel_lons.shape, longitude),
        np.full(pixel_lats.shape, latitude),
        pixel_lons,
        pixel_lats,
    )
    window = population_counts[row_start:row_stop, column_start:column_stop]
    selected = np.isfinite(window) & (distances <= radius_m)
    return float(window[selected].sum()) if selected.any() else np.nan

