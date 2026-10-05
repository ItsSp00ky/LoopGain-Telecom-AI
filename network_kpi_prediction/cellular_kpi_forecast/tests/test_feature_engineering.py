"""
tests/test_features.py
Unit tests for src/features.py (damped trends, Fourier harmonics, zero lookahead autoregressive lags).
"""

import os
import sys
import unittest
import numpy as np
import pandas as pd

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.feature_engineering import (
    compute_damped_trend, extract_time_features, compute_autoregressive_features,
    get_feature_columns, get_all_feature_columns
)


class TestFeatures(unittest.TestCase):
    def test_damped_trend_bounded(self):
        # Verify asymptotic saturation over large time horizons
        t_1year = np.array([365.25])
        t_10year = np.array([3652.5])
        trend_1 = compute_damped_trend(t_1year, phi=0.5)[0]
        trend_10 = compute_damped_trend(t_10year, phi=0.5)[0]
        self.assertGreater(trend_10, trend_1)
        # Asymptote is 1 / phi = 2.0
        self.assertLess(trend_10, 2.0)

    def test_extract_time_features(self):
        dates = pd.date_range('2026-01-01', periods=30, freq='D')
        df = pd.DataFrame({'date': dates})
        feat_df = extract_time_features(df)
        cols = get_feature_columns()
        for c in cols:
            self.assertIn(c, feat_df.columns)
        self.assertEqual(len(feat_df), 30)
        # Verify trend_linear has been strictly purged
        self.assertNotIn('trend_linear', cols)
        self.assertNotIn('trend_linear', feat_df.columns)

    def test_autoregressive_features_zero_lookahead(self):
        y = np.arange(25, dtype=float)
        ar = compute_autoregressive_features(y)
        self.assertEqual(ar.shape, (25, 4))
        # Zero lookahead verification:
        # lag_1 at index 5 must strictly equal y[4]
        self.assertEqual(ar[5, 0], y[4])
        # lag_7 at index 10 must strictly equal y[3]
        self.assertEqual(ar[10, 1], y[3])
        # Non-negative rolling volatility
        self.assertTrue((ar[:, 3] >= 0.0).all())


if __name__ == '__main__':
    unittest.main()
