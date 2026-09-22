import gzip
import json
import tempfile
import unittest
from pathlib import Path

import geopandas as gpd
import h3
from shapely.geometry import Polygon, box

from antenna_cell_placement.building_features import load_building_footprints, compute_building_features_per_hex

HEX = h3.latlng_to_cell(32.8872, 13.1913, 8)


def hex_gdf():
    boundary = h3.cell_to_boundary(HEX)
    return gpd.GeoDataFrame(
        {"h3_index": [HEX]},
        geometry=[Polygon([(lon, lat) for lat, lon in boundary])],
        crs="EPSG:4326",
    )


def square(lat, lon, half=0.0001):
    return box(lon - half, lat - half, lon + half, lat + half)


class BuildingFeaturesTests(unittest.TestCase):
    def test_load_building_footprints_reads_geojson_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tile.csv.gz"
            with gzip.open(path, "wt") as f:
                for lat in (32.887, 32.888):
                    feature = {
                        "type": "Feature",
                        "properties": {"height": -1.0, "confidence": -1.0},
                        "geometry": square(lat, 13.191).__geo_interface__,
                    }
                    f.write(json.dumps(feature) + "\n")
            gdf = load_building_footprints([path])
        self.assertEqual(len(gdf), 2)
        self.assertEqual(str(gdf.crs), "EPSG:4326")

    def test_counts_only_buildings_inside_hex(self):
        lat, lon = h3.cell_to_latlng(HEX)
        buildings = gpd.GeoDataFrame(
            geometry=[
                square(lat, lon),
                square(lat + 0.0005, lon),
                square(lat, lon + 0.0005),
                square(lat + 0.5, lon + 0.5),  # far outside the hex
            ],
            crs="EPSG:4326",
        )
        result = compute_building_features_per_hex(hex_gdf(), buildings)
        self.assertEqual(len(result), 1)
        row = result.iloc[0]
        self.assertEqual(row["building_count"], 3)
        self.assertGreater(row["building_density_per_km2"], 0)
        self.assertGreater(row["total_building_area_m2"], 0)
        self.assertAlmostEqual(row["avg_building_area_m2"], row["total_building_area_m2"] / 3, places=1)
        self.assertTrue(0 < row["built_up_ratio"] < 1)

    def test_empty_hex_gets_zeros(self):
        buildings = gpd.GeoDataFrame(geometry=[square(31.0, 20.0)], crs="EPSG:4326")
        row = compute_building_features_per_hex(hex_gdf(), buildings).iloc[0]
        self.assertEqual(row["building_count"], 0)
        self.assertEqual(row["built_up_ratio"], 0.0)
        self.assertEqual(row["avg_building_area_m2"], 0.0)


if __name__ == "__main__":
    unittest.main()
