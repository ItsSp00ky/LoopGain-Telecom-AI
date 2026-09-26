import unittest

import geopandas as gpd
import h3
from shapely.geometry import LineString, Point, Polygon

from antenna_cell_placement.osm_features import compute_osm_features_per_hex

HEX = h3.latlng_to_cell(32.8872, 13.1913, 8)


def hex_gdf():
    boundary = h3.cell_to_boundary(HEX)
    return gpd.GeoDataFrame(
        {"h3_index": [HEX]},
        geometry=[Polygon([(lon, lat) for lat, lon in boundary])],
        crs="EPSG:4326",
    )


class OSMFeaturesTests(unittest.TestCase):
    def test_road_density_and_poi_categories(self):
        lat, lon = h3.cell_to_latlng(HEX)
        roads = gpd.GeoDataFrame(
            geometry=[LineString([(lon - 0.05, lat), (lon + 0.05, lat)])],
            crs="EPSG:4326",
        )
        pois = gpd.GeoDataFrame(
            {
                "amenity": ["hospital", None, "school"],
                "shop": [None, "supermarket", None],
                "landuse": [None, None, None],
            },
            geometry=[Point(lon, lat), Point(lon + 0.001, lat), Point(lon + 0.5, lat + 0.5)],
            crs="EPSG:4326",
        )
        row = compute_osm_features_per_hex(hex_gdf(), roads, pois).iloc[0]

        self.assertEqual(row["h3_index"], HEX)
        self.assertTrue(0.5 < row["osm_road_length_km"] < 1.5)
        self.assertGreater(row["osm_road_density_km_per_km2"], 0)
        self.assertEqual(row["poi_count"], 2)
        self.assertEqual(row["poi_count_hospital"], 1)
        self.assertEqual(row["poi_count_commercial"], 1)
        self.assertEqual(row["poi_count_school"], 0)

    def test_no_roads_or_pois_gives_zeros(self):
        row = compute_osm_features_per_hex(hex_gdf(), None, None).iloc[0]
        self.assertEqual(row["osm_road_length_km"], 0.0)
        self.assertEqual(row["poi_count"], 0)
        self.assertEqual(row["poi_count_industrial"], 0)


if __name__ == "__main__":
    unittest.main()
