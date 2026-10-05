"""Step 15 assets stay isolated and fail visible quality checks."""

import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from antenna_cell_placement.operator_assets import evaluate_operator_assets
from antenna_cell_placement.pilot import _pilot_asset_review, prepare_measurements
import h3
from antenna_cell_placement.collected_opencellid import COLUMNS


class OperatorAssetTests(unittest.TestCase):
    def create_export(self, root: Path):
        (root / "source_manifest.json").write_text(json.dumps({
            "source_organization": "test operator", "authorization_reference": "test-only",
            "snapshot_utc": "2026-09-22T00:00:00Z",
            "field_sources": {"sites.latitude": "survey"}}))
        pd.DataFrame([{"site_id": "S1", "latitude": "32.88", "longitude": "13.18",
                       "coordinate_accuracy_m": "5", "surveyed_at_utc": "2026-09-01T00:00:00Z",
                       "status": "active"}]).to_csv(root / "sites.csv", index=False)
        pd.DataFrame([{"sector_id": "C1", "site_id": "S1", "antenna_id": "A1", "radio": "LTE",
                       "mcc": "606", "mnc": "0", "area": "1", "cell": "123",
                       "frequency_mhz": "1800", "bandwidth_mhz": "20", "azimuth_deg": "120",
                       "mechanical_tilt_deg": "2", "electrical_tilt_deg": "4", "height_m": "30",
                       "tx_power_dbm": "43", "feeder_loss_db": "1"}]).to_csv(root / "sectors.csv", index=False)
        pd.DataFrame([{"antenna_id": "A1", "model": "Test model", "gain_dbi": "17",
                       "pattern_reference": "internal pattern"}]).to_csv(root / "antenna_catalog.csv", index=False)

    def test_valid_export_is_review_only_and_report_has_no_asset_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_export(root)
            output = root / "report.json"
            report = evaluate_operator_assets(root, output_path=output, observed_path=None)
            self.assertEqual(report["status"], "review")
            self.assertEqual(report["metrics"]["sites"]["valid_rows"], 1)
            self.assertEqual(report["metrics"]["sectors"]["valid_rows"], 1)
            self.assertEqual(report["metrics"]["sectors"]["engineering_complete_pct"], 100)
            self.assertNotIn("S1", output.read_text())
            self.assertNotIn("C1", output.read_text())
            self.assertIsNone(report["thresholds"])
            self.assertEqual(report["metrics"]["field_provenance"]["declared_fields"], 1)

    def test_broken_link_and_missing_engineering_are_excluded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_export(root)
            sectors = pd.read_csv(root / "sectors.csv", dtype=str, keep_default_na=False)
            sectors.loc[0, "site_id"] = "missing"
            sectors.loc[0, "bandwidth_mhz"] = ""
            sectors.to_csv(root / "sectors.csv", index=False)
            report = evaluate_operator_assets(root, observed_path=None)
            self.assertEqual(report["metrics"]["sectors"]["valid_rows"], 0)
            self.assertEqual(report["metrics"]["sectors"]["broken_site_links"], 1)
            self.assertEqual(report["metrics"]["sectors"]["engineering_complete_pct"], 0)

    def test_thresholds_require_independent_survey(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_export(root)
            (root / "quality_thresholds.json").write_text(json.dumps({
                "minimum_valid_site_pct": 95, "minimum_valid_sector_pct": 95,
                "minimum_engineering_complete_pct": 95,
                "maximum_survey_median_error_m": 20,
                "minimum_observed_cell_match_pct": 50,
                "maximum_site_age_days": 90}))
            report = evaluate_operator_assets(root, observed_path=None)
            self.assertTrue(report["checks"]["valid_site_pct"])
            self.assertIsNone(report["checks"]["survey_median_error_m"])
            self.assertIsNone(report["checks"]["observed_cell_match_pct"])
            self.assertTrue(report["checks"]["site_freshness"])
            self.assertEqual(report["status"], "review")

    def test_exact_cell_identity_and_survey_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_export(root)
            pd.DataFrame([{"site_id": "S1", "latitude": "32.88", "longitude": "13.18"}]).to_csv(
                root / "survey_checkpoints.csv", index=False)
            observed = root / "observed.csv"
            pd.DataFrame([["LTE", 606, 0, 1, 123, 4, 13.18, 32.88, 1000, 5, 1,
                           1700000000, 1780000000, 0]], columns=COLUMNS).to_csv(observed, index=False)
            report = evaluate_operator_assets(root, observed_path=observed)
            self.assertEqual(report["metrics"]["observed_cell_match"]["matched_sectors"], 1)
            self.assertEqual(report["metrics"]["survey_checkpoints"]["median_m"], 0)

    def test_pilot_asset_review_counts_exact_and_ambiguous_identities(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.create_export(root)
            frame = prepare_measurements(pd.DataFrame([
                dict(mcc=606, mnc=0, net_type='LTE', lac=1, cell_id=123,
                     lat=32.88, lon=13.18, dbm=-90., device='A',
                     measured_at=pd.Timestamp('2026-09-23T12:00:00Z'), review_eligible=True),
                dict(mcc=606, mnc=0, net_type='LTE', lac=1, cell_id=124,
                     lat=32.88, lon=13.18, dbm=-90., device='A',
                     measured_at=pd.Timestamp('2026-09-23T12:00:00Z'), review_eligible=True)]))
            pilot = {'h3_r7': h3.latlng_to_cell(32.88, 13.18, 7)}
            result = _pilot_asset_review(frame, pilot, root)
            self.assertEqual((result['matched_identities'], result['missing_identities'],
                              result['ambiguous_identities'], result['complete_matched_identities']),
                             (1, 1, 0, 1))
            self.assertNotIn('S1', json.dumps(result))
            sectors = pd.read_csv(root / 'sectors.csv', dtype=str, keep_default_na=False)
            sectors.loc[1] = sectors.loc[0]
            sectors.loc[1, 'sector_id'] = 'C2'
            sectors.to_csv(root / 'sectors.csv', index=False)
            result = _pilot_asset_review(frame, pilot, root)
            self.assertEqual((result['matched_identities'], result['ambiguous_identities']), (0, 1))


if __name__ == "__main__":
    unittest.main()
