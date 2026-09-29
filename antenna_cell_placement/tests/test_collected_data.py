import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from shapely.geometry import box

from antenna_cell_placement.collected_data import (
    CELLMAPPER_RELATIVE, annotate_measurements, cellmapper_raw_records,
    load_cellmapper, load_measurements,
)
from antenna_cell_placement.data_cleaning import deduplicate_radio_towers
from antenna_cell_placement.opencellid import COLUMNS, load_cells


class CollectedDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.boundary = patch('antenna_cell_placement.collected_data._libya_boundary', return_value=box(10, 20, 25, 34))
        self.boundary.start()
        self.addCleanup(self.boundary.stop)

    def cell(self, **changes):
        row = dict(mcc=606, mnc=0, rat='LTE', region_id=123, site_id=200, cell_id=51201,
                   latitude=32.8, longitude=13.2, first_seen_iso='2025-01-01', last_seen_iso='2026-01-01',
                   earfcn_channels='1700,1700', bands='3', bandwidth_mhz=20, tower_type='MACRO',
                   loc_ta_method1=None, loc_ta_method2=None, loc_ss_method1=None, verified=False)
        row.update(changes)
        return row

    def write_cells(self, rows):
        path = self.root / CELLMAPPER_RELATIVE
        path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(path, index=False)

    def test_scope_quarantine_duplicates_and_missing_bandwidth(self):
        self.write_cells([self.cell(), self.cell(), self.cell(mnc=1), self.cell(latitude=0), self.cell(cell_id=-1)])
        cells, rejected = load_cellmapper(self.root)
        self.assertEqual(len(cells), 2)
        self.assertEqual(len(rejected), 2)
        raw = cellmapper_raw_records(self.root)
        towers = deduplicate_radio_towers(raw)
        self.assertEqual(len(towers), 2)  # Same tower identifier in different networks.
        self.assertTrue(towers.total_bandwidth_mhz.isna().all())
        self.assertTrue(towers.visible.isna().all())
        self.assertEqual(towers.channel_count.tolist(), [1, 1])

    def test_measurements_do_not_create_sites_and_filter_bad_evidence(self):
        row = dict(mcc=606, mnc=0, lac=123, cell_id=51201, net_type='LTE',
                   lat=32.8, lon=13.2, measured_at='2026-01-01T00:00:00Z', device='test',
                   dbm=-90, accuracy=10, neighboring=False)
        pd.DataFrame([row, row, dict(row, accuracy=500, cell_id=51202),
                      dict(row, measured_at='2099-01-01'), dict(row, lat=0)]).to_csv(self.root / 'phone.csv', index=False)
        measurements, rejected = load_measurements(self.root, as_of='2026-09-26')
        self.assertEqual(len(measurements), 2)
        self.assertEqual(len(rejected), 2)
        self.assertEqual(int(measurements.review_eligible.sum()), 1)
        self.assertTrue(cellmapper_raw_records(self.root).empty)
        candidates = pd.DataFrame({'canonical_latitude': [32.8, 30], 'canonical_longitude': [13.2, 20], 'planning_priority_score': [50, 70]})
        result = annotate_measurements(candidates, measurements)
        self.assertEqual(result.measurement_count_1km.tolist(), [1, 0])
        self.assertEqual(result.planning_priority_score.tolist(), [50, 70])
        self.assertEqual(result.measurement_nearest_distance_m.iloc[0], 0)
        self.assertTrue(pd.isna(result.measurement_mnc_0_lte_median_dbm_1km.iloc[1]))

    def test_extended_opencellid_export(self):
        row = ['LTE', 606, 0, 1, 1, 1, 13.2, 32.8, 1000, 5, 1, 1704067200, 1735689600, 0]
        path = self.root / 'ocid.csv'
        frame = pd.DataFrame([row], columns=COLUMNS)
        frame['provider'] = 'source label'
        frame.to_csv(path, index=False)
        with patch('antenna_cell_placement.opencellid._libya_boundary', return_value=box(10, 20, 25, 34)):
            cells, rejected, _ = load_cells(path, as_of='2026-01-01')
        self.assertEqual(len(cells), 1)
        self.assertTrue(rejected.empty)

    def test_conflicting_locations_never_form_a_false_midpoint(self):
        self.write_cells([self.cell(), self.cell(cell_id=51202, longitude=23.0)])
        towers = deduplicate_radio_towers(cellmapper_raw_records(self.root))
        self.assertEqual(len(towers), 2)
        self.assertTrue(towers.location_conflict.all())
        self.assertEqual(set(towers.longitude), {13.2, 23.0})

    def test_absent_optional_collection(self):
        self.assertTrue(load_cellmapper(self.root)[0].empty)
        self.assertTrue(load_measurements(self.root)[0].empty)


if __name__ == '__main__':
    unittest.main()
