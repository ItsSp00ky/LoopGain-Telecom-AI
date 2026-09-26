import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import h3
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from shapely.geometry import Polygon

from antenna_cell_placement.landcover_features import compute_landcover_pct_per_hex

HEX = h3.latlng_to_cell(32.8872, 13.1913, 8)


def hex_gdf():
    boundary = h3.cell_to_boundary(HEX)
    return gpd.GeoDataFrame(
        {"h3_index": [HEX]},
        geometry=[Polygon([(lon, lat) for lat, lon in boundary])],
        crs="EPSG:4326",
    )


def write_raster(path, gdf, west_class=50, east_class=80, size=200):
    minx, miny, maxx, maxy = gdf.total_bounds
    pad = 0.002
    data = np.full((size, size), east_class, dtype=np.uint8)
    data[:, : size // 2] = west_class
    transform = from_bounds(minx - pad, miny - pad, maxx + pad, maxy + pad, size, size)
    with rasterio.open(
        path, "w", driver="GTiff", height=size, width=size, count=1,
        dtype="uint8", crs="EPSG:4326", transform=transform, nodata=0,
    ) as dst:
        dst.write(data, 1)


class LandcoverFeaturesTests(unittest.TestCase):
    def test_half_builtup_half_water_hex(self):
        gdf = hex_gdf()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "worldcover.tif"
            write_raster(path, gdf)
            result = compute_landcover_pct_per_hex(gdf, tile_paths=[path])

        self.assertEqual(len(result), 1)
        row = result.iloc[0]
        self.assertEqual(row["h3_index"], HEX)
        self.assertTrue(35 <= row["landcover_builtup_pct"] <= 65)
        self.assertTrue(35 <= row["landcover_water_pct"] <= 65)
        self.assertAlmostEqual(row["landcover_builtup_pct"] + row["landcover_water_pct"], 100.0, delta=0.5)
        self.assertEqual(row["landcover_cropland_pct"], 0.0)

    def test_all_bare_hex(self):
        gdf = hex_gdf()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "worldcover.tif"
            write_raster(path, gdf, west_class=60, east_class=60)
            row = compute_landcover_pct_per_hex(gdf, tile_paths=[path]).iloc[0]
        self.assertAlmostEqual(row["landcover_bare_pct"], 100.0, delta=0.5)


if __name__ == "__main__":
    unittest.main()
