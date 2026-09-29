import unittest

import geopandas as gpd
import numpy as np
import pandas as pd
from affine import Affine
from scipy.spatial import cKDTree
from shapely.geometry import Point, box

from antenna_cell_placement.config import CRS_PROJECTED_LIBYA
from antenna_cell_placement.feature_engineering import GeospatialFeatureExtractor
from antenna_cell_placement.opencellid import projected


class FeatureEngineeringTests(unittest.TestCase):
    def setUp(self):
        self.sites = pd.DataFrame({
            "canonical_longitude": [13.0, 13.01, 13.03],
            "canonical_latitude": [32.0, 32.0, 32.0],
            "has_libyana": [1, 0, 1],
            "has_almadar": [0, 1, 1],
        })
        self.coords = projected(self.sites.canonical_longitude, self.sites.canonical_latitude)
        self.extractor = GeospatialFeatureExtractor()
        self.extractor._loaded = True
        for name in ("pop", "dem"):
            setattr(self.extractor, name + "_arr", np.zeros((2, 2)))
            setattr(self.extractor, name + "_shape", (2, 2))
            setattr(self.extractor, "inv_" + name, Affine.identity())
        self.extractor.road_tree = cKDTree(self.coords)
        self.extractor.place_tree = cKDTree(self.coords[:1])
        self.extractor.places_df = gpd.GeoDataFrame({
            "featurename_en": ["Example"], "popplaceclasstitle": ["Town"],
        }, geometry=[Point(*self.coords[0])], crs=CRS_PROJECTED_LIBYA)
        self.extractor.admin2_gdf = gpd.GeoDataFrame({
            "adm2_name": ["Unknown"], "adm1_name": ["Example"],
        }, geometry=[box(0, 0, 1e7, 1e7)], crs=CRS_PROJECTED_LIBYA)
        self.extractor.set_existing_sites(self.sites)

    def test_density_counts_match_direct_queries(self):
        for existing in (False, True):
            features = self.extractor.extract_features(
                self.sites.canonical_longitude, self.sites.canonical_latitude, existing
            )
            for radius in (1, 3, 5, 10):
                expected = [
                    len(self.extractor.site_tree_all.query_ball_point(point, radius * 1000))
                    - int(existing) for point in self.coords
                ]
                np.testing.assert_array_equal(features[f"site_density_{radius}km"], expected)

    def test_other_operator_nearest_site_is_not_skipped(self):
        features = self.extractor.extract_features(
            self.sites.canonical_longitude, self.sites.canonical_latitude, True
        )
        expected = round(np.linalg.norm(self.coords[0] - self.coords[1]), 1)
        self.assertAlmostEqual(features.loc[0, "dist_to_almadar_site_m"], expected, places=1)
        self.assertAlmostEqual(features.loc[1, "dist_to_libyana_site_m"], expected, places=1)

    def test_replacing_sites_clears_old_operator_trees(self):
        self.extractor.set_existing_sites(self.sites.iloc[[0]])
        self.assertIsNone(self.extractor.site_tree_almadar)
        self.assertEqual(self.extractor.site_tree_libyana.n, 1)

    def test_invalid_coordinates_fail_before_loading_layers(self):
        for lons, lats in (([13.0], [32.0, 33.0]), ([np.nan], [32.0]), ([13.0], [91.0])):
            with self.subTest(lons=lons, lats=lats):
                with self.assertRaisesRegex(ValueError, "coordinates"):
                    GeospatialFeatureExtractor().extract_features(lons, lats)


if __name__ == "__main__":
    unittest.main()
