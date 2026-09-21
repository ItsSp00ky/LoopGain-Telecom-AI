import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import geopandas as gpd
import h3
import pandas as pd
from shapely.geometry import box

from antenna_cell_placement.ookla import (
    OoklaPerformanceExtractor,
    aggregate_supported_h3,
    prepare_ookla_tiles,
    verify_ookla_manifest,
)


class OoklaTests(unittest.TestCase):
    def tiles(self):
        geometry = box(13.179, 32.879, 13.181, 32.881)
        return gpd.GeoDataFrame(
            {
                "avg_d_kbps": [10_000, 20_000, 99_000],
                "avg_u_kbps": [2_000, 4_000, 99_000],
                "avg_lat_ms": [50, 30, 1],
                "tests": [10, 30, 4],
                "devices": [5, 8, 2],
                "quadkey": ["a", "a", "a"],
                "quarter": ["2025Q2", "2025Q3", "2025Q4"],
            },
            geometry=[geometry, geometry, geometry],
            crs="EPSG:4326",
        )

    def test_support_filter_and_weighted_aggregation_are_explicit(self):
        prepared, quality = prepare_ookla_tiles(self.tiles())
        summary = aggregate_supported_h3(prepared)

        self.assertEqual(quality["supported_tile_quarter_rows"], 2)
        self.assertEqual(quality["below_support_threshold_rows"], 1)
        self.assertEqual(len(summary), 1)
        self.assertAlmostEqual(summary.loc[0, "ookla_download_mbps"], 17.5)
        self.assertAlmostEqual(summary.loc[0, "ookla_upload_mbps"], 3.5)
        self.assertAlmostEqual(summary.loc[0, "ookla_latency_ms"], 35.0)
        self.assertEqual(summary.loc[0, "ookla_test_count"], 40)
        self.assertEqual(summary.loc[0, "ookla_supported_quarters"], 2)
        self.assertNotIn("devices", summary.columns)

    def test_context_is_non_mutating_and_unsupported_units_stay_missing(self):
        cell = h3.latlng_to_cell(32.88, 13.18, 7)
        candidates = pd.DataFrame(
            {
                "candidate_id": ["a", "b"],
                "recommendation_rank": [1, 2],
                "planning_priority_score": [80.0, 70.0],
                "h3_r7": [cell, h3.latlng_to_cell(25.0, 20.0, 7)],
            }
        )
        original = candidates.copy(deep=True)
        result = OoklaPerformanceExtractor(self.tiles()).add_context(candidates)

        pd.testing.assert_frame_equal(candidates, original)
        pd.testing.assert_frame_equal(result[original.columns], original)
        self.assertTrue(result.loc[0, "ookla_data_available"])
        self.assertAlmostEqual(result.loc[0, "ookla_download_mbps"], 17.5)
        self.assertFalse(result.loc[1, "ookla_data_available"])
        self.assertTrue(pd.isna(result.loc[1, "ookla_download_mbps"]))

    def test_required_schema_is_enforced(self):
        with self.assertRaises(KeyError):
            prepare_ookla_tiles(self.tiles().drop(columns="devices"))

    def test_manifest_verification_detects_source_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            data_dir = Path(temporary)
            records = []
            for name, content in (("quarter.zip", b"source"), ("subset.gpkg", b"subset")):
                path = data_dir / name
                path.write_bytes(content)
                records.append(
                    {
                        "filename": name,
                        "bytes": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                )
            manifest = {
                "license": "CC-BY-NC-SA-4.0",
                "periods": ["2025Q2", "2025Q3", "2025Q4", "2026Q1"],
                "source_files": [records[0]],
                "libya_subset": records[1],
            }
            manifest_path = data_dir / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertTrue(verify_ookla_manifest(manifest_path, data_dir)["verified"])
            (data_dir / "subset.gpkg").write_bytes(b"changed")
            self.assertFalse(verify_ookla_manifest(manifest_path, data_dir)["verified"])


if __name__ == "__main__":
    unittest.main()
