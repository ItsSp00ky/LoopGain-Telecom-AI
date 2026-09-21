import tempfile
import unittest
from pathlib import Path

import pandas as pd

from antenna_cell_placement.opencellid import COLUMNS, load_cells, annotate_candidates


class OpenCellIDTests(unittest.TestCase):
    def load(self, rows, header=False):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cells.csv'
            pd.DataFrame(rows, columns=COLUMNS).to_csv(path, index=False, header=header)
            return load_cells(path, as_of='2026-09-13T00:00:00Z')

    def row(self, **changes):
        row = dict(zip(COLUMNS, ['LTE', 606, 0, 1, 12345, 4, 13.18, 32.88,
                                 1000, 5, 1, 1700000000, 1780000000, 0]))
        row.update(changes)
        return row

    def test_header_and_first_row_preserved(self):
        for header in (False, True):
            cells, _, report = self.load([self.row()], header)
            self.assertEqual(len(cells), 1)
            self.assertEqual(cells.iloc[0]['operator'], 'Libyana')
            self.assertEqual(cells.iloc[0]['unit_semantics'], 'PCI')
            self.assertTrue(cells.iloc[0]['range_is_estimated'])
            self.assertEqual(report['input_rows'], 1)
            self.assertEqual(report['unexpected_changeable_values'], 0)
            self.assertEqual(report['unexpected_average_signal_values'], 0)

    def test_deprecated_columns_are_reported_but_not_decision_inputs(self):
        cells, _, report = self.load([self.row(changeable=0, averageSignal=-75)])
        self.assertEqual(len(cells), 1)
        self.assertEqual(report['unexpected_changeable_values'], 1)
        self.assertEqual(report['unexpected_average_signal_values'], 1)
        self.assertTrue(cells.loc[0, 'review_eligible'])

    def test_identity_includes_operator_area_and_radio(self):
        rows = [self.row(), self.row(net=1), self.row(area=2), self.row(radio='UMTS'),
                self.row(updated=1781000000, samples=10), self.row(net=3)]
        cells, _, report = self.load(rows)
        self.assertEqual(len(cells), 5)
        self.assertEqual(report['duplicate_identity_rows'], 1)
        self.assertEqual(set(cells.operator), {'Libyana', 'Al-Madar', 'Unknown'})
        lib = cells[(cells.net == 0) & (cells.area == 1) & (cells.radio == 'LTE')]
        self.assertEqual(lib.iloc[0].samples, 10)

    def test_validation_and_dates(self):
        cells, rejected, _ = self.load([
            self.row(), self.row(lat=0), self.row(mcc=999), self.row(cell=1.5),
            self.row(cell=2, updated=2000000000), self.row(cell=3, samples=1),
            self.row(cell=4, updated=1700000001), self.row(cell=5, created='bad')])
        self.assertEqual(len(rejected), 3)
        self.assertEqual(int(cells.review_eligible.sum()), 1)
        self.assertEqual(int((~cells.timestamp_valid).sum()), 2)
        self.assertEqual(str(cells.updated_utc.dt.tz), 'UTC')
        self.assertEqual(cells.loc[cells.cell == 12345, 'updated_utc'].iloc[0],
                         pd.Timestamp(1780000000, unit='s', tz='UTC'))

    def test_proximity_does_not_change_ranking_and_empty_is_unknown(self):
        cells, _, _ = self.load([self.row(range=99999999)])
        candidates = pd.DataFrame({'canonical_longitude': [13.18, 20.0],
                                   'canonical_latitude': [32.88, 30.0],
                                   'recommendation_rank': [1, 2]})
        annotated = annotate_candidates(candidates, cells)
        self.assertEqual(annotated.opencellid_review_required.tolist(), [True, False])
        self.assertEqual(annotated.recommendation_rank.tolist(), [1, 2])
        self.assertTrue(annotated.opencellid_almadar_distance_m.isna().all())
        empty = annotate_candidates(candidates, cells.iloc[:0])
        self.assertTrue(empty.opencellid_recent_distance_m.isna().all())
        self.assertFalse(empty.opencellid_review_required.any())


if __name__ == '__main__':
    unittest.main()
