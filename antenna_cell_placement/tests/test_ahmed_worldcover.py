import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import h3
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin

from antenna_cell_placement.worldcover import (
    WORLDCOVER_BASE_URL,
    WORLDCOVER_DOI,
    WORLDCOVER_LICENSE,
    WORLDCOVER_VERSION,
    WorldCoverExtractor,
    tile_name,
    tile_name_for_coordinate,
    verify_manifest,
)


class WorldCoverTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temporary.name)
        self.tile_path = self.data_dir / tile_name(30, 12)
        values = np.full((300, 300), 60, dtype=np.uint8)
        values[150, 150] = 80
        with rasterio.open(
            self.tile_path,
            "w",
            driver="GTiff",
            width=300,
            height=300,
            count=1,
            dtype="uint8",
            crs="EPSG:4326",
            transform=from_origin(12.0, 33.0, 0.01, 0.01),
            nodata=0,
        ) as target:
            target.write(values, 1)

    def tearDown(self):
        self.temporary.cleanup()

    def test_tile_naming_handles_three_degree_grid_and_negative_longitude(self):
        self.assertEqual(
            tile_name_for_coordinate(32.9, 13.2),
            "ESA_WorldCover_10m_2021_v200_N30E012_Map.tif",
        )
        self.assertEqual(
            tile_name_for_coordinate(-0.1, -0.1),
            "ESA_WorldCover_10m_2021_v200_S03W003_Map.tif",
        )

    def test_point_classes_preserve_water_and_missing_as_distinct_states(self):
        frame = pd.DataFrame(
            {
                "canonical_latitude": [31.495, 32.5, 20.0],
                "canonical_longitude": [13.505, 12.5, 20.0],
            }
        )
        result = WorldCoverExtractor(self.data_dir).add_point_features(frame)
        self.assertEqual(result.loc[0, "worldcover_class_code"], 80)
        self.assertTrue(result.loc[0, "worldcover_is_water"])
        self.assertEqual(result.loc[1, "worldcover_class_code"], 60)
        self.assertFalse(result.loc[1, "worldcover_is_water"])
        self.assertFalse(result.loc[2, "worldcover_data_available"])
        self.assertTrue(pd.isna(result.loc[2, "worldcover_class_code"]))

    def test_h3_context_is_area_weighted_and_deterministic(self):
        cell = h3.latlng_to_cell(32.5, 12.5, 7)
        frame = pd.DataFrame({"h3_r7": [cell, cell]})
        extractor = WorldCoverExtractor(self.data_dir)
        first = extractor.add_h3_context(frame)
        second = extractor.add_h3_context(frame)
        pd.testing.assert_frame_equal(first, second)
        self.assertEqual(first.loc[0, "worldcover_h3_dominant_class_code"], 60)
        self.assertAlmostEqual(first.loc[0, "worldcover_h3_bare_fraction"], 1.0)
        self.assertFalse(first.loc[0, "worldcover_review_required"])

    def test_manifest_verification_detects_source_content(self):
        digest = hashlib.sha256(self.tile_path.read_bytes()).hexdigest()
        manifest = {
            "dataset": WORLDCOVER_VERSION,
            "doi": WORLDCOVER_DOI,
            "license": WORLDCOVER_LICENSE,
            "source_base_url": WORLDCOVER_BASE_URL,
            "tile_count": 1,
            "total_bytes": self.tile_path.stat().st_size,
            "tiles": [
                {
                    "filename": self.tile_path.name,
                    "bytes": self.tile_path.stat().st_size,
                    "sha256": digest,
                }
            ]
        }
        (self.data_dir / "manifest.json").write_text(json.dumps(manifest))
        self.assertTrue(verify_manifest(self.data_dir)["verified"])
        self.tile_path.write_bytes(b"changed")
        self.assertFalse(verify_manifest(self.data_dir)["verified"])


if __name__ == "__main__":
    unittest.main()
