"""Terrain features in metres, independent of a raster's pixel spacing."""

from __future__ import annotations

import math

import numpy as np
from pyproj import Geod, Transformer
import rasterio


GEOD = Geod(ellps="WGS84")
PROMINENCE_RADIUS_M = 3000.0


class TerrainSampler:
    def __init__(self, array: np.ndarray, transform, crs="EPSG:4326"):
        if not crs:
            raise ValueError("Terrain raster must declare a CRS")
        self.array = np.asarray(array, dtype=np.float32)
        self.transform = transform
        self.inverse = ~transform
        self.crs = str(crs)
        self.to_raster = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
        self.to_wgs84 = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)

    @classmethod
    def from_raster(cls, path):
        with rasterio.open(path) as source:
            data = source.read(1, masked=True).astype(np.float32).filled(np.nan)
            return cls(data, source.transform, source.crs)

    def _pixel_lonlat(self, row: int, col: int) -> tuple[float, float]:
        x, y = self.transform @ (col + 0.5, row + 0.5)
        return self.to_wgs84.transform(x, y)

    def sample(self, lon: float, lat: float, *, require_full_window: bool = False) -> dict[str, float | bool]:
        x, y = self.to_raster.transform(lon, lat)
        col_f, row_f = self.inverse @ (x, y)
        col, row = math.floor(col_f), math.floor(row_f)
        empty = {"elevation_m": math.nan, "elevation_prominence_3km": math.nan,
                 "terrain_slope_deg": math.nan, "terrain_data_available": False,
                 "window_complete": False}
        height, width = self.array.shape
        if not (0 <= row < height and 0 <= col < width):
            return empty
        elevation = float(self.array[row, col])
        if not math.isfinite(elevation):
            return empty
        center_lon, center_lat = self._pixel_lonlat(row, col)
        right_lon, right_lat = self._pixel_lonlat(row, col + 1)
        down_lon, down_lat = self._pixel_lonlat(row + 1, col)
        x_step = GEOD.inv(center_lon, center_lat, right_lon, right_lat)[2]
        y_step = GEOD.inv(center_lon, center_lat, down_lon, down_lat)[2]
        if x_step <= 0 or y_step <= 0:
            return empty
        x_radius = math.ceil(PROMINENCE_RADIUS_M / x_step)
        y_radius = math.ceil(PROMINENCE_RADIUS_M / y_step)
        full = (row - y_radius >= 0 and row + y_radius < height and
                col - x_radius >= 0 and col + x_radius < width)
        if require_full_window and not full:
            return {**empty, "elevation_m": elevation}
        r0, r1 = max(0, row - y_radius), min(height, row + y_radius + 1)
        c0, c1 = max(0, col - x_radius), min(width, col + x_radius + 1)
        rows = (np.arange(r0, r1) - row) * y_step
        cols = (np.arange(c0, c1) - col) * x_step
        within_radius = rows[:, None] ** 2 + cols[None, :] ** 2 <= PROMINENCE_RADIUS_M ** 2
        window = self.array[r0:r1, c0:c1]
        valid = within_radius & np.isfinite(window)
        prominence = elevation - float(window[valid].mean()) if valid.any() else math.nan
        slope = math.nan
        if 0 < row < height - 1 and 0 < col < width - 1:
            neighbors = self.array[[row, row, row + 1, row - 1], [col + 1, col - 1, col, col]]
            if np.isfinite(neighbors).all():
                dx = (float(neighbors[0]) - float(neighbors[1])) / (2 * x_step)
                dy = (float(neighbors[2]) - float(neighbors[3])) / (2 * y_step)
                slope = math.degrees(math.atan(math.hypot(dx, dy)))
        return {"elevation_m": elevation, "elevation_prominence_3km": prominence,
                "terrain_slope_deg": slope,
                "terrain_data_available": math.isfinite(prominence) and math.isfinite(slope),
                "window_complete": full}
