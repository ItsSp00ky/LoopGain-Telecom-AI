"""
tests/test_pipeline.py
Automated Unit Tests for Config, Feature Engineering, S-Tier Models, and Export Hub.
"""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import unittest
import numpy as np
import pandas as pd
import json

from src.kpi_config import KPI_CONFIG, KPI_KEYS, apply_bounds, check_sla_compliance
from src.feature_engineering import (
    compute_damped_trend, extract_time_features, compute_autoregressive_features,
    get_feature_columns, get_all_feature_columns
)
from src.model_definitions import (
    TargetTransformer, compute_mase, compute_wape, evaluate_predictions,
    DampedFourierRidgeModel, HybridTrendSeasonalModel,
    AdaptiveSeasonalBaseline, QuantileIntervalEstimator, apply_boundary_anchoring
)
from src.report_export import (
    build_carrier_markdown_report, build_carrier_json_payload
)
from src.visualization import (
    plot_single_kpi, plot_carrier_grid, plot_multiband_kpi
)
from src.temporal_splitting import split_carrier_data, export_splits, load_splits

class TestConfig(unittest.TestCase):
    def test_kpi_completeness(self):
        self.assertEqual(len(KPI_KEYS), 10)
        for kpi in KPI_KEYS:
            self.assertIn('name', KPI_CONFIG[kpi])
            self.assertIn('unit', KPI_CONFIG[kpi])
            self.assertIn('category', KPI_CONFIG[kpi])

    def test_apply_bounds(self):
        # rrc_setup_sr bounded [0, 100]
        clipped = apply_bounds(np.array([-5.0, 50.0, 105.0]), 'rrc_setup_sr')
        np.testing.assert_array_equal(clipped, np.array([0.0, 50.0, 100.0]))

        # handover_intra_sr bounded [0, 1]
        clipped_ratio = apply_bounds(np.array([-0.2, 0.95, 1.5]), 'handover_intra_sr')
        np.testing.assert_array_equal(clipped_ratio, np.array([0.0, 0.95, 1.0]))

        # downtime_sec bounded >= 0
        clipped_down = apply_bounds(np.array([-10.0, 500.0]), 'downtime_sec')
        np.testing.assert_array_equal(clipped_down, np.array([0.0, 500.0]))

    def test_sla_compliance(self):
        self.assertTrue(check_sla_compliance(99.5, 'rrc_setup_sr'))
        self.assertFalse(check_sla_compliance(98.5, 'rrc_setup_sr'))
        self.assertTrue(check_sla_compliance(0.2, 'erab_drop_rate'))
        self.assertFalse(check_sla_compliance(0.8, 'erab_drop_rate'))

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
        # Generate synthetic series with linear trend + weekly harmonic
        np.random.seed(42)
        n = 100
        t = np.arange(n)
        y = 50.0 + 0.1 * t + 2.0 * np.sin(2 * np.pi * t / 7) + np.random.normal(0, 0.2, n)
        X = np.column_range = np.column_stack([t, np.sin(2 * np.pi * t / 7), np.cos(2 * np.pi * t / 7)])
        
        model = HybridTrendSeasonalModel('rrc_setup_sr')
        model.fit(X, y)
        preds = model.predict(X)
        self.assertEqual(len(preds), n)
        self.assertFalse(np.isnan(preds).any())
        self.assertTrue((preds >= 0.0).all() and (preds <= 100.0).all())

    def test_adaptive_seasonal_baseline(self):
        n = 70
        dows = np.array([i % 7 for i in range(n)])
        # Day 0 has mean 10, Day 1 has mean 20, etc.
        y = (dows + 1) * 10.0 + np.random.normal(0, 0.1, n)
        X = np.zeros((n, 2))
        
        model = AdaptiveSeasonalBaseline('dl_throughput_mbps')
        model.fit(X, y, day_of_week=dows)
        preds = model.predict(X, day_of_week=dows)
        self.assertEqual(len(preds), n)
        # Verify day 0 prediction is ~ 10, day 1 is ~ 20
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
        # Non-crossing guarantee: lower <= y_pred <= upper
        self.assertTrue((lower <= y_pred + 1e-6).all())
        self.assertTrue((upper >= y_pred - 1e-6).all())
        # Bounds check
        self.assertTrue((lower >= 0.0).all())
        self.assertTrue((upper <= 100.0).all())

class TestExport(unittest.TestCase):
    def test_untruncated_markdown_export(self):
        dates = pd.date_range('2026-09-18', periods=365, freq='D')
        hist_dates = pd.date_range('2025-09-18', periods=365, freq='D')
        
        hist_df = pd.DataFrame({'date': hist_dates, 'rrc_setup_sr': np.full(365, 99.6)})
        fc_df = pd.DataFrame({'date': dates, 'rrc_setup_sr': np.full(365, 99.7)})
        
        metrics = {'metrics_summary': {'350': {'rrc_setup_sr': {'rmse': 0.1, 'best_model': 'Ridge'}}}}
        md_bytes = build_carrier_markdown_report(350, 'rrc_setup_sr', hist_df, fc_df, metrics)
        md_text = md_bytes.decode('utf-8')
        
        # Verify complete 365 daily rows in table
        daily_rows = [l for l in md_text.splitlines() if l.startswith("| 202")]
        self.assertEqual(len(daily_rows), 365)
        self.assertNotIn("...", md_text)
        self.assertIn("O-RAN Non-RT RIC SMO (A1 Policy)", md_text)

    def test_json_payload(self):
        dates = pd.date_range('2026-09-18', periods=365, freq='D')
        fc_df = pd.DataFrame({'date': dates, 'rrc_setup_sr': np.full(365, 99.7)})
        json_bytes = build_carrier_json_payload(350, fc_df)
        parsed = json.loads(json_bytes.decode('utf-8'))
        self.assertEqual(parsed['total_projections'], 365)
        self.assertEqual(len(parsed['data']), 365)
        self.assertEqual(parsed['interface'], 'O-RAN_NON_RT_RIC_SMO_A1_POLICY')


class TestPlotEngine(unittest.TestCase):
    def setUp(self):
        self.hist_dates = pd.date_range('2025-09-18', periods=20, freq='D')
        self.fc_dates = pd.date_range('2026-09-18', periods=20, freq='D')
        self.hist_df = pd.DataFrame({'date': self.hist_dates, 'carrier_freq': 350})
        self.fc_df = pd.DataFrame({'date': self.fc_dates, 'carrier_freq': 350})
        for k in KPI_KEYS:
            self.hist_df[k] = 99.5
            self.fc_df[k] = 99.6
            self.fc_df[f"{k}_p05"] = 99.2
            self.fc_df[f"{k}_p95"] = 99.9

    def test_single_kpi_plot(self):
        fig = plot_single_kpi(350, 'rrc_setup_sr', self.hist_df, self.fc_df, dpi=100)
        self.assertIsNotNone(fig)
        import matplotlib.pyplot as plt
        plt.close(fig)

    def test_carrier_grid_plot(self):
        fig = plot_carrier_grid(350, self.hist_df, self.fc_df, dpi=100)
        self.assertIsNotNone(fig)
        import matplotlib.pyplot as plt
        plt.close(fig)

    def test_multiband_plot(self):
        fig = plot_multiband_kpi('rrc_setup_sr', self.hist_df, self.fc_df, dpi=100)
        self.assertIsNotNone(fig)
        import matplotlib.pyplot as plt
        plt.close(fig)

class TestSplitEngine(unittest.TestCase):
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
        import tempfile
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
