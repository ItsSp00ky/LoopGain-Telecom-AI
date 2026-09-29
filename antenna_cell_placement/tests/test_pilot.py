"""Tests of evidence isolation, held-out evaluation, and missing-input gates."""

import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

import h3
import pandas as pd

from antenna_cell_placement.collected_data import annotate_measurements
from antenna_cell_placement.pilot import (
    _pilot_split, build_pilot_review, chronological_baseline, match_sector_identities,
    prepare_measurements, rf_readiness, select_pilot, service_summary,
)
from antenna_cell_placement.reconciliation import reconcile_locations


class PilotTests(unittest.TestCase):
    def measurements(self, **changes):
        row = dict(mcc=606, mnc=0, net_type='LTE', lac=1, cell_id=101,
                   lat=32.88, lon=13.18, dbm=-90., rsrp=-100., device='A',
                   measured_at=pd.Timestamp('2026-09-23T12:00:00Z'), review_eligible=True)
        row.update(changes)
        return row

    def towers(self):
        return pd.DataFrame([
            dict(mcc='606', mnc='0', rat='LTE', region_id='1', site_id='10',
                 latitude=32.88, longitude=13.18, location_group=1, location_conflict=True,
                 source_verified=True, first_seen_ms=1704067200000, last_seen_ms=1788134400000, source_files='A'),
            dict(mcc='606', mnc='0', rat='LTE', region_id='1', site_id='10',
                 latitude=32.88, longitude=14.18, location_group=2, location_conflict=True,
                 source_verified=False, first_seen_ms=1704067200000, last_seen_ms=1767225600000, source_files='B'),
        ])

    def test_service_never_mixes_operator_or_radio(self):
        frame = prepare_measurements(pd.DataFrame([self.measurements(), self.measurements(mnc=1, dbm=-60), self.measurements(net_type='UMTS', dbm=-75)]))
        summary = service_summary(frame)
        self.assertEqual(len(summary), 3)
        self.assertEqual(set(summary.median_dbm), {-90, -60, -75})
        self.assertTrue(summary.loc[summary.net_type.eq('UMTS'), 'median_lte_rsrp_dbm'].isna().all())
        candidates = pd.DataFrame({'canonical_latitude': [32.88], 'canonical_longitude': [13.18]})
        annotated = annotate_measurements(candidates, frame)
        self.assertEqual(annotated.measurement_mnc_0_lte_median_dbm_1km.iloc[0], -90)
        self.assertEqual(annotated.measurement_mnc_1_lte_median_dbm_1km.iloc[0], -60)

    def test_stationary_repeats_do_not_dominate_daily_blocks(self):
        rows = [self.measurements(dbm=-100)] * 100 + [self.measurements(dbm=-60, device='B')]
        summary = service_summary(prepare_measurements(pd.DataFrame(rows)))
        self.assertEqual(summary.median_dbm.iloc[0], -80)
        self.assertEqual(summary.sample_count.iloc[0], 101)

    def test_temporal_baseline_uses_train_only_and_reports_unseen_areas(self):
        train = prepare_measurements(pd.DataFrame([self.measurements(dbm=-90)]))
        holdout = prepare_measurements(pd.DataFrame([self.measurements(dbm=-70, measured_at=pd.Timestamp('2026-09-26T12:00:00Z')),
                                                    self.measurements(mnc=1, dbm=-30, measured_at=pd.Timestamp('2026-09-26T12:00:00Z'))]))
        result = chronological_baseline(train, holdout)
        self.assertEqual(result['mae_db'], 20)
        self.assertEqual(result['bias_db'], -20)
        self.assertEqual(result['matched_blocks'], 1)
        self.assertEqual(result['coverage_pct'], 50)
        with self.assertRaises(AssertionError):
            chronological_baseline(train, train)

    def test_empty_holdout_does_not_claim_validation_success(self):
        frame = prepare_measurements(pd.DataFrame([self.measurements()]))
        result = chronological_baseline(frame, frame.iloc[:0])
        self.assertEqual(result['status'], 'unavailable')
        self.assertIsNone(result['mae_db'])

    def test_frozen_split_rejects_new_days_and_preserves_holdout(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'snapshot.json'
            config.write_text(json.dumps({'version': 1, 'training_days': ['2026-09-23'],
                                          'holdout_days': ['2026-09-26'],
                                          'pilot_h3_r7': h3.latlng_to_cell(32.88, 13.18, 7),
                                          'source_sha256': {}}))
            frame = prepare_measurements(pd.DataFrame([
                self.measurements(),
                self.measurements(measured_at=pd.Timestamp('2026-09-26T12:00:00Z'))]))
            train, holdout, _ = _pilot_split(frame, config, [])
            self.assertEqual(set(train.day), {'2026-09-23'})
            self.assertEqual(set(holdout.day), {'2026-09-26'})
            newer = prepare_measurements(pd.DataFrame([
                self.measurements(measured_at=pd.Timestamp('2026-09-27T12:00:00Z'))]))
            with self.assertRaisesRegex(ValueError, 'observed days'):
                _pilot_split(pd.concat([frame, newer]), config, [])
            changed = json.loads(config.read_text())
            changed['source_sha256'] = {'changed.csv': 'invalid'}
            config.write_text(json.dumps(changed))
            with self.assertRaisesRegex(ValueError, 'source snapshot changed'):
                _pilot_split(frame, config, [])

    def test_second_holdout_day_does_not_enter_training(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'snapshot.json'
            config.write_text(json.dumps({'version': 2, 'training_days': ['2026-09-23'],
                                          'holdout_days': ['2026-09-26', '2026-09-28'],
                                          'pilot_h3_r7': h3.latlng_to_cell(32.88, 13.18, 7),
                                          'source_sha256': {}}))
            frame = prepare_measurements(pd.DataFrame([
                self.measurements(),
                self.measurements(measured_at=pd.Timestamp('2026-09-26T12:00:00Z')),
                self.measurements(measured_at=pd.Timestamp('2026-09-28T12:00:00Z'))]))
            train, holdout, _ = _pilot_split(frame, config, [])
            self.assertEqual(set(train.day), {'2026-09-23'})
            self.assertEqual(set(holdout.day), {'2026-09-26', '2026-09-28'})

    def test_identity_match_requires_full_network_and_area(self):
        frame = prepare_measurements(pd.DataFrame([self.measurements()]))
        cells = pd.DataFrame([dict(mcc=606, mnc=1, rat='LTE', region_id=1, cell_id=101),
                              dict(mcc=606, mnc=0, rat='LTE', region_id=2, cell_id=101)])
        self.assertEqual(match_sector_identities(frame, cells)['matched_identities'], 0)
        cells.loc[0, 'mnc'] = 0
        self.assertEqual(match_sector_identities(frame, cells)['matched_identities'], 1)

    def test_received_signal_and_omni_sentinel_are_not_engineering_inputs(self):
        result = rf_readiness(pd.DataFrame([dict(signal_rsrp_dbm=-60, azimuth_bearing_deg=999, bandwidth_mhz=20)]), {'matched_identities': 1})
        self.assertFalse(result['simulation_enabled'])
        self.assertEqual(result['engineering_complete_sectors'], 0)
        self.assertEqual(result['valid_field_counts']['azimuth_bearing_deg'], 0)
        self.assertIn('tx_power_dbm', result['missing_everywhere'])

    def test_unique_verified_recent_location_is_only_provisional(self):
        report = reconcile_locations(self.towers(), as_of='2026-09-26')
        self.assertEqual(report['preferred_for_review'], 1)
        self.assertEqual(report['survey_resolved_identities'], 0)
        self.assertEqual(len(report['decisions'][0]['alternatives']), 2)

    def test_ambiguous_or_newer_competitor_prevents_preference(self):
        towers = self.towers()
        towers['source_verified'] = True
        self.assertEqual(reconcile_locations(towers, as_of='2026-09-26')['preferred_for_review'], 0)
        towers.loc[1, 'source_verified'] = False
        towers.loc[1, 'last_seen_ms'] = 1788998400000
        self.assertEqual(reconcile_locations(towers, as_of='2026-09-26')['preferred_for_review'], 0)
        towers.loc[1, 'last_seen_ms'] = 4102444800000
        self.assertEqual(reconcile_locations(towers, as_of='2026-09-26')['preferred_for_review'], 0)

    def test_empty_data_writes_valid_empty_outputs(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            with patch('antenna_cell_placement.pilot.load_measurements', return_value=(pd.DataFrame(), pd.DataFrame())), patch('antenna_cell_placement.pilot.load_cellmapper', return_value=(pd.DataFrame(), pd.DataFrame())):
                report = build_pilot_review(directory, directory, towers=self.towers())
            self.assertEqual(report['status'], 'no_eligible_measurements')
            self.assertEqual(report['pilot']['status'], 'unavailable')
            self.assertFalse(report['rf_readiness']['simulation_enabled'])
            self.assertEqual(json.loads((Path(directory) / 'measured_service_areas.geojson').read_text())['features'], [])
            self.assertNotIn('NaN', (Path(directory) / 'pilot_review.json').read_text())

    def test_pilot_excludes_conflicted_anchors_and_is_order_independent(self):
        area = h3.latlng_to_cell(32.88, 13.18, 7)
        points = [h3.cell_to_latlng(cell) for cell in sorted(h3.cell_to_children(area, 9))[:5]]
        rows = [self.measurements(lat=points[index % 5][0], lon=points[index % 5][1], cell_id=101 + index % 3) for index in range(100)]
        frame = prepare_measurements(pd.DataFrame(rows))
        towers = self.towers()
        result = select_pilot(frame, towers)
        self.assertIn('h3_r7', result)
        self.assertEqual(result['nearby_source_verified_nonconflicting_references'], 0)
        self.assertEqual(result, select_pilot(frame.sample(frac=1, random_state=42), towers))
        self.assertFalse(result['rf_validation_ready'])


if __name__ == '__main__':
    unittest.main()
