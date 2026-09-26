"""
tests/test_clean.py
Unit tests for src/clean.py (Data cleaning, schema validation, bounds clipping, and loaders).
"""

import os
import sys
import unittest
import numpy as np
import pandas as pd

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.clean import clean_telemetry, validate_telemetry, load_clean_data


class TestClean(unittest.TestCase):
    def test_clean_telemetry_bounds_and_duplicates(self):
        raw = pd.DataFrame({
            'date': ['2026-01-01', '2026-01-01', '2026-01-02'],
            'carrier_freq': [350, 350, 350],
            'rrc_setup_sr': [105.0, 99.8, -5.0],  # Out of bounds [0, 100]
            'dl_throughput_mbps': [-2.0, 10.5, np.nan],  # Negative and NaN
            'dt': ['2026-01-01', '2026-01-01', '2026-01-02']  # Redundant column
        })
        cleaned = clean_telemetry(raw)
        
        # Duplicate on 2026-01-01 should be dropped
        self.assertEqual(len(cleaned), 2)
        # 'dt' column should be removed
        self.assertNotIn('dt', cleaned.columns)
        # rrc_setup_sr should be clipped to [0, 100]
        self.assertEqual(cleaned['rrc_setup_sr'].iloc[0], 99.8)
        self.assertEqual(cleaned['rrc_setup_sr'].iloc[1], 0.0)
        # dl_throughput should be non-negative and NaN forward-filled
        self.assertEqual(cleaned['dl_throughput_mbps'].iloc[0], 10.5)
        self.assertEqual(cleaned['dl_throughput_mbps'].iloc[1], 10.5)

    def test_validate_telemetry(self):
        df = pd.DataFrame({
            'date': pd.date_range('2026-01-01', periods=10, freq='D'),
            'carrier_freq': [350] * 5 + [1700] * 5,
            'rrc_setup_sr': [99.5] * 10
        })
        report = validate_telemetry(df)
        self.assertEqual(report['total_rows'], 10)
        self.assertEqual(report['missing_values'], 0)
        self.assertEqual(report['carriers'], [350, 1700])
        self.assertEqual(report['date_range']['start'], '2026-01-01')
        self.assertEqual(report['date_range']['end'], '2026-01-10')

    def test_load_clean_data(self):
        df = load_clean_data()
        self.assertGreater(len(df), 2000)
        self.assertIn('carrier_freq', df.columns)
        self.assertIn('rrc_setup_sr', df.columns)
        self.assertNotIn('dt', df.columns)


if __name__ == '__main__':
    unittest.main()
