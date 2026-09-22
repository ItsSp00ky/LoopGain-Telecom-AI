"""
tests/test_models.py
Unit tests for src/models.py (Transformers, Ridge, Hybrid, Baseline, Quantiles, and metrics).
"""

import os
import sys
import unittest
import numpy as np
import pandas as pd

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.models import (
    TargetTransformer, compute_mase, compute_wape, evaluate_predictions,
    DampedFourierRidgeModel, HybridTrendSeasonalModel,
    AdaptiveSeasonalBaseline, QuantileIntervalEstimator, apply_boundary_anchoring
)


class TestModels(unittest.TestCase):
    def test_target_transformer(self):
        trans = TargetTransformer('log1p')
        raw = np.array([0.0, 10.0, 100.0])
        t = trans.transform(raw)
        inv = trans.inverse_transform(t, 'downtime_sec')
        np.testing.assert_allclose(raw, inv, rtol=1e-5)

    def test_time_series_metrics(self):
        y_train = np.array([10.0, 11.0, 12.0, 10.0, 11.0, 12.0, 10.0, 11.0, 12.0, 10.0])
        y_true = np.array([10.0, 11.0, 12.0])
        y_pred = np.array([10.1, 10.9, 12.1])
        m = evaluate_predictions(y_true, y_pred, y_train)
        self.assertIn('rmse', m)
        self.assertIn('mae', m)
        self.assertIn('wape', m)
        self.assertIn('mase', m)
        self.assertIn('r2_bench', m)
        self.assertLess(m['mase'], 1.0)
        self.assertGreater(m['r2_bench'], 0.5)

    def test_boundary_anchoring(self):
        preds = np.array([90.0, 92.0, 94.0, 96.0])
        last_obs = 95.0
        anchored = apply_boundary_anchoring(preds, last_obs, 'availability_pct', decay_rate=0.5)
        # Day 0 must match last observation exactly
        self.assertAlmostEqual(anchored[0], 95.0, places=4)
        # Boundary offset must decay toward zero over time
        initial_offset = abs(anchored[0] - preds[0])
        future_offset = abs(anchored[3] - preds[3])
        self.assertLess(future_offset, initial_offset)

    def test_hybrid_trend_seasonal_model(self):
        np.random.seed(42)
        n = 100
        t = np.arange(n)
        y = 50.0 + 0.1 * t + 2.0 * np.sin(2 * np.pi * t / 7) + np.random.normal(0, 0.2, n)
        X = np.column_stack([t, np.sin(2 * np.pi * t / 7), np.cos(2 * np.pi * t / 7)])
        
        model = HybridTrendSeasonalModel('rrc_setup_sr')
        model.fit(X, y)
        preds = model.predict(X)
        self.assertEqual(len(preds), n)
        self.assertFalse(np.isnan(preds).any())
        self.assertTrue((preds >= 0.0).all() and (preds <= 100.0).all())

    def test_adaptive_seasonal_baseline(self):
        n = 70
        dows = np.array([i % 7 for i in range(n)])
        y = (dows + 1) * 10.0 + np.random.normal(0, 0.1, n)
        X = np.zeros((n, 2))
        
        model = AdaptiveSeasonalBaseline('dl_throughput_mbps')
        model.fit(X, y, day_of_week=dows)
        preds = model.predict(X, day_of_week=dows)
        self.assertEqual(len(preds), n)
        self.assertAlmostEqual(preds[0], 10.0, delta=1.0)
        self.assertAlmostEqual(preds[1], 20.0, delta=1.0)

    def test_quantile_intervals(self):
        np.random.seed(42)
        n = 100
        X = np.random.randn(n, 4)
        residuals = np.random.normal(0, 2.0, n)
        y_pred = np.full(n, 50.0)
        
        q_est = QuantileIntervalEstimator('rrc_setup_sr')
        q_est.fit(X, residuals)
        lower, upper = q_est.predict_intervals(X, y_pred)
        
        self.assertEqual(len(lower), n)
        self.assertEqual(len(upper), n)
        self.assertTrue((lower <= y_pred + 1e-6).all())
        self.assertTrue((upper >= y_pred - 1e-6).all())
        self.assertTrue((lower >= 0.0).all())
        self.assertTrue((upper <= 100.0).all())


if __name__ == '__main__':
    unittest.main()
