import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import from_origin

from antenna_cell_placement.nightlights import (
    EXPECTED_MONTHS,
    NightLightsExtractor,
    _nearest_distance_km,
    verify_viirs_manifest,
)


class NightLightsTests(unittest.TestCase):
    def _raster(self, directory: Path, name: str, values) -> Path:
        path = directory / name
        array = np.asarray(values, dtype="float32")
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            width=array.shape[1],
            height=array.shape[0],
            count=1,
            dtype="float32",
            crs="EPSG:4326",
            transform=from_origin(10, 34, 1, 1),
            nodata=-9999,
        ) as target:
            target.write(array, 1)
        return path

    def test_zero_radiance_is_darkness_when_coverage_is_supported(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            pairs = {}
            for month in EXPECTED_MONTHS:
                pairs[month] = (
                    self._raster(directory, f"{month}_r.tif", [[0, 9]]),
                    self._raster(directory, f"{month}_c.tif", [[5, 2]]),
                )
            candidates = pd.DataFrame(
                {
                    "canonical_latitude": [33.5, 33.5],
                    "canonical_longitude": [10.5, 11.5],
                    "worldcover_is_water": [False, False],
                }
            )
            original = candidates.copy(deep=True)
            result = NightLightsExtractor(
                pairs, pd.DataFrame(columns=["latitude", "longitude"])
            ).add_context(candidates)

            pd.testing.assert_frame_equal(candidates, original)
            self.assertTrue(result.loc[0, "viirs_data_available"])
            self.assertEqual(result.loc[0, "viirs_median_radiance"], 0)
            self.assertFalse(result.loc[1, "viirs_data_available"])
            self.assertTrue(pd.isna(result.loc[1, "viirs_median_radiance"]))

    def test_water_is_ineligible_even_with_supported_radiance(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            pairs = {
                month: (
                    self._raster(directory, f"{month}_r.tif", [[10]]),
                    self._raster(directory, f"{month}_c.tif", [[8]]),
                )
                for month in EXPECTED_MONTHS
            }
            result = NightLightsExtractor(
                pairs, pd.DataFrame(columns=["latitude", "longitude"])
            ).add_context(
                pd.DataFrame(
                    {
                        "canonical_latitude": [33.5],
                        "canonical_longitude": [10.5],
                        "worldcover_is_water": [True],
                    }
                )
            )
            self.assertFalse(result.loc[0, "viirs_data_available"])

    def test_known_flare_distance_is_geodesic_and_deterministic(self):
        flares = pd.DataFrame({"latitude": [30.0], "longitude": [20.0]})
        distances = _nearest_distance_km(
            np.array([30.0, 31.0]), np.array([20.0, 20.0]), flares
        )
        self.assertAlmostEqual(distances[0], 0.0)
        self.assertAlmostEqual(distances[1], 111.2, delta=0.2)

    def test_required_candidate_coordinates_are_enforced(self):
        with self.assertRaises(KeyError):
            NightLightsExtractor(
                {month: (Path("x"), Path("y")) for month in EXPECTED_MONTHS},
                pd.DataFrame(columns=["latitude", "longitude"]),
            ).add_context(pd.DataFrame({"canonical_latitude": [30.0]}))

    def test_manifest_verification_detects_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            products = []
            for month in EXPECTED_MONTHS:
                records = []
                for suffix in ("radiance", "coverage"):
                    path = directory / f"{month}_{suffix}.tif"
                    path.write_bytes(f"{month}-{suffix}".encode())
                    records.append(self._record(path))
                products.append(
                    {"month": month, "radiance": records[0], "cloudfree_count": records[1]}
                )
            flare_source = directory / "flares.kml"
            flare_subset = directory / "flares.csv"
            flare_source.write_bytes(b"source")
            flare_subset.write_bytes(b"latitude,longitude\n")
            manifest = {
                "license": "ODbL-1.0",
                "periods": list(EXPECTED_MONTHS),
                "products": products,
                "gas_flare_catalog": {
                    "source_record": self._record(flare_source),
                    "libya_subset": self._record(flare_subset),
                },
            }
            manifest_path = directory / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertTrue(verify_viirs_manifest(manifest_path, directory)["verified"])
            flare_subset.write_bytes(b"changed")
            self.assertFalse(verify_viirs_manifest(manifest_path, directory)["verified"])

    @staticmethod
    def _record(path: Path):
        content = path.read_bytes()
        return {
            "filename": path.name,
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }


if __name__ == "__main__":
    unittest.main()
