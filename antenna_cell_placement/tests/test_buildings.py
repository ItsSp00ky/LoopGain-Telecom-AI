import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import geopandas as gpd
import h3
import pandas as pd
from shapely.geometry import Polygon, box

from antenna_cell_placement.buildings import (
    BuildingFootprintExtractor,
    LICENSE,
    LICENSE_URL,
    SNAPSHOT_DATE,
    SOURCE_URL,
    prepare_buildings,
    verify_manifest,
)


class BuildingFootprintTests(unittest.TestCase):
    def test_h3_context_is_deterministic_area_based_and_non_mutating(self):
        latitude, longitude = 32.88, 13.18
        cell = h3.latlng_to_cell(latitude, longitude, 7)
        buildings = gpd.GeoDataFrame(
            {"osm_id": ["1"]},
            geometry=[
                box(
                    longitude - 0.0001,
                    latitude - 0.0001,
                    longitude + 0.0001,
                    latitude + 0.0001,
                )
            ],
            crs="EPSG:4326",
        )
        candidates = pd.DataFrame(
            {
                "h3_r7": [cell],
                "worldcover_class_code": [50],
                "worldcover_h3_built_up_fraction": [0.5],
            }
        )
        original = candidates.copy(deep=True)
        extractor = BuildingFootprintExtractor(buildings=buildings)
        first = extractor.add_h3_context(candidates)
        second = extractor.add_h3_context(candidates)
        pd.testing.assert_frame_equal(candidates, original)
        pd.testing.assert_frame_equal(first, second)
        self.assertEqual(first.loc[0, "osm_building_count_h3"], 1)
        self.assertGreater(first.loc[0, "osm_building_footprint_area_m2_h3"], 0)
        self.assertGreater(first.loc[0, "osm_building_coverage_ratio_h3"], 0)
        self.assertTrue(first.loc[0, "osm_building_observed_h3"])
        self.assertFalse(first.loc[0, "osm_building_review_required"])

    def test_missing_mapped_building_is_review_not_false_zero_evidence(self):
        cell = h3.latlng_to_cell(32.88, 13.18, 7)
        buildings = gpd.GeoDataFrame(
            geometry=[box(20.0, 20.0, 20.001, 20.001)], crs="EPSG:4326"
        )
        candidates = pd.DataFrame(
            {
                "h3_r7": [cell],
                "worldcover_class_code": [50],
                "worldcover_h3_built_up_fraction": [0.5],
            }
        )
        result = BuildingFootprintExtractor(buildings=buildings).add_h3_context(
            candidates
        )
        self.assertEqual(result.loc[0, "osm_building_count_h3"], 0)
        self.assertFalse(result.loc[0, "osm_building_observed_h3"])
        self.assertTrue(result.loc[0, "osm_building_context_available"])
        self.assertTrue(result.loc[0, "osm_building_review_required"])

    def test_context_without_worldcover_h3_summary_supports_single_assessment(self):
        cell = h3.latlng_to_cell(32.88, 13.18, 7)
        buildings = gpd.GeoDataFrame(
            geometry=[box(20.0, 20.0, 20.001, 20.001)], crs="EPSG:4326"
        )
        candidate = pd.DataFrame({"h3_r7": [cell], "worldcover_class_code": [10]})

        result = BuildingFootprintExtractor(buildings=buildings).add_h3_context(
            candidate
        )

        self.assertEqual(result.loc[0, "osm_building_count_h3"], 0)
        self.assertFalse(result.loc[0, "osm_building_review_required"])

    def test_geometry_quality_repairs_invalid_and_removes_exact_duplicates(self):
        bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
        duplicate = box(2, 2, 3, 3)
        source = gpd.GeoDataFrame(
            geometry=[bowtie, duplicate, duplicate], crs="EPSG:4326"
        )
        prepared, quality = prepare_buildings(source)
        self.assertEqual(quality["invalid_geometry_rows_before_repair"], 1)
        self.assertEqual(quality["invalid_geometry_rows_after_repair"], 0)
        self.assertEqual(quality["duplicate_geometry_rows_removed"], 1)
        self.assertTrue(prepared.geometry.is_valid.all())

    def test_manifest_verifies_metadata_size_and_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            files = []
            for name, content in (("source.zip", b"archive"), ("source.gpkg", b"gpkg")):
                path = data_dir / name
                path.write_bytes(content)
                files.append(
                    {
                        "filename": name,
                        "bytes": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                )
            manifest = {
                "source_url": SOURCE_URL,
                "snapshot_date": SNAPSHOT_DATE,
                "license": LICENSE,
                "license_url": LICENSE_URL,
                "files": files,
            }
            (data_dir / "manifest.json").write_text(json.dumps(manifest))
            self.assertTrue(verify_manifest(data_dir)["verified"])
            (data_dir / "source.gpkg").write_bytes(b"changed")
            self.assertFalse(verify_manifest(data_dir)["verified"])


if __name__ == "__main__":
    unittest.main()
