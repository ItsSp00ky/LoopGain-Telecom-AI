"""
tests/test_split.py
Unit tests for src/split.py (Chronological splitting, leak-free assertions, and disk export/load).
"""

import os
import sys
import unittest
import tempfile
import numpy as np
import pandas as pd

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.temporal_splitting import split_carrier_data, export_splits, load_splits


class TestSplit(unittest.TestCase):
    def test_split_carrier_data_integrity(self):
        dates = pd.date_range('2025-01-01', periods=100, freq='D')
        df = pd.DataFrame({
            'date': np.concatenate([dates, dates]),
            'carrier_freq': [350] * 100 + [1700] * 100,
            'rrc_setup_sr': 99.5
        })
        train, val, test, manifest = split_carrier_data(df, 0.70, 0.15, 0.15)
        self.assertEqual(len(train) + len(val) + len(test), 200)
        for c in [350, 1700]:
            c_train = train[train['carrier_freq'] == c]
            c_val = val[val['carrier_freq'] == c]
            c_test = test[test['carrier_freq'] == c]
            self.assertEqual(len(c_train), 70)
            self.assertEqual(len(c_val), 15)
            self.assertEqual(len(c_test), 15)
            self.assertLess(c_train['date'].max(), c_val['date'].min())
            self.assertLess(c_val['date'].max(), c_test['date'].min())

    def test_export_and_load_splits(self):
        dates = pd.date_range('2025-01-01', periods=50, freq='D')
        df = pd.DataFrame({'date': dates, 'carrier_freq': 350, 'rrc_setup_sr': 99.5})
        train, val, test, manifest = split_carrier_data(df, 0.6, 0.2, 0.2)
        with tempfile.TemporaryDirectory() as tmpdir:
            export_splits(train, val, test, manifest, output_dir=tmpdir)
            t_load, v_load, te_load, m_load = load_splits(input_dir=tmpdir)
            self.assertEqual(len(t_load), len(train))
            self.assertEqual(len(v_load), len(val))
            self.assertEqual(len(te_load), len(test))
            self.assertEqual(m_load['summary']['total_rows'], 50)


if __name__ == '__main__':
    unittest.main()
