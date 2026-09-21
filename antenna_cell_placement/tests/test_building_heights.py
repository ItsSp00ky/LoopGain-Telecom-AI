import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from antenna_cell_placement.building_heights import (
    HEIGHT_SOURCE_URL,
    extract_osm_tag,
    parse_height_m,
    prepare_height_tags,
    verify_height_manifest,
)
from antenna_cell_placement.buildings import LICENSE, LICENSE_URL, SNAPSHOT_DATE


class BuildingHeightTests(unittest.TestCase):
    def test_height_parser_handles_declared_units_without_floor_assumptions(self):
        self.assertEqual(parse_height_m("10.5"), (10.5, "metres"))
        self.assertEqual(parse_height_m("12 m"), (12.0, "metres"))
        self.assertEqual(parse_height_m("30 ft"), (9.144, "feet"))
        height, unit = parse_height_m("7'4\"")
        self.assertAlmostEqual(height, 2.2352)
        self.assertEqual(unit, "feet_inches")
        self.assertEqual(parse_height_m("3-4"), (None, "invalid_format"))
        self.assertEqual(parse_height_m("0.5"), (None, "outside_plausible_range"))

    def test_osm_tag_extraction_is_exact(self):
        tags = '"building:levels"=>"3","height"=>"10","source:height"=>"survey"'
        self.assertEqual(extract_osm_tag(tags, "height"), "10")
        self.assertEqual(extract_osm_tag(tags, "source:height"), "survey")
        self.assertIsNone(extract_osm_tag(tags, "roof:height"))

    def test_preparation_preserves_unknown_provenance_and_invalid_values(self):
        source = pd.DataFrame(
            {
                "other_tags": [
                    '"height"=>"9","source:height"=>"survey"',
                    '"building:levels"=>"4","height"=>"about 12"',
                ]
            }
        )
        result = prepare_height_tags(source)
        self.assertEqual(result.loc[0, "height_m"], 9.0)
        self.assertEqual(result.loc[0, "height_source_raw"], "survey")
        self.assertTrue(pd.isna(result.loc[1, "height_m"]))
        self.assertTrue(pd.isna(result.loc[1, "height_source_raw"]))

    def test_height_manifest_verifies_size_hash_and_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            source = directory / "source.osm.pbf"
            source.write_bytes(b"source")
            manifest = {
                "source_url": HEIGHT_SOURCE_URL,
                "snapshot_date": SNAPSHOT_DATE,
                "license": LICENSE,
                "license_url": LICENSE_URL,
                "file": {
                    "filename": source.name,
                    "bytes": source.stat().st_size,
                    "sha256": hashlib.sha256(b"source").hexdigest(),
                },
            }
            manifest_path = directory / "height_manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertTrue(verify_height_manifest(manifest_path, source)["verified"])
            source.write_bytes(b"changed")
            self.assertFalse(verify_height_manifest(manifest_path, source)["verified"])


if __name__ == "__main__":
    unittest.main()
