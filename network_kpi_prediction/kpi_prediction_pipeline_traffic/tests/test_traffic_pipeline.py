"""
test_traffic_pipeline.py
Unit Test Suite for the 4G Network Traffic KPI Prediction Pipeline.
Validates data ingestion, cleaning, chronological splitting, feature engineering,
and model metrics without temporal data leakage.
"""

import os
import sys
import unittest
import numpy as np
import pandas as pd
from pathlib import Path

# Add project root to sys.path
_PKG_ROOT = Path(__file__).resolve().parent.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from src.clean import load_raw_data, validate_and_regularize, detect_and_treat_anomalies
from src.split import chronological_split
from src.features import create_time_features, get_feature_columns
from src.models import calculate_metrics, SeasonalNaiveModel


class TestTrafficClean(unittest.TestCase):
    def setUp(self):
        # Create a small synthetic raw dataset with comma-formatted numbers
        self.tmp_csv = _PKG_ROOT / "tests" / "scratch_test_raw.csv"
        self.tmp_csv.parent.mkdir(parents=True, exist_ok=True)
        dates = pd.date_range("2026-01-01", periods=30, freq="D")
        raw_df = pd.DataFrame({
            'Date': [d.strftime("%m/%d/%y") for d in dates],
            '4G Data Volume (GB)': [f"{1000 + i * 10:,.2f}" for i in range(30)]
        })
        raw_df.to_csv(self.tmp_csv, index=False)

    def tearDown(self):
        if self.tmp_csv.exists():
            self.tmp_csv.unlink()

    def test_load_raw_data_and_cleaning(self):
        df = load_raw_data(self.tmp_csv)
        self.assertIn("date", df.columns)
        self.assertIn("kpi_volume_gb", df.columns)
        self.assertEqual(len(df), 30)
        self.assertTrue(pd.api.types.is_numeric_dtype(df["kpi_volume_gb"]))
        self.assertEqual(df["kpi_volume_gb"].iloc[0], 1000.0)

    def test_validate_and_regularize_missing_dates(self):
        # DataFrame with missing dates
        dates = pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-04"])
        df = pd.DataFrame({
            "date": dates,
            "kpi_volume_gb": [100.0, 110.0, 130.0]
        })
        reg_df = validate_and_regularize(df)
        self.assertEqual(len(reg_df), 4)  # 2026-01-03 interpolated
        self.assertAlmostEqual(reg_df.loc[reg_df["date"] == "2026-01-03", "kpi_volume_gb"].iloc[0], 120.0)

    def test_detect_and_treat_anomalies(self):
        # Create a series with a clear injected outlier
        dates = pd.date_range("2026-01-01", periods=45, freq="D")
        np.random.seed(42)
        base = 5000.0 + 200.0 * np.sin(2 * np.pi * np.arange(45) / 7.0)
        base[20] = 50000.0  # massive 10x spike
        df = pd.DataFrame({"date": dates, "kpi_volume_gb": base})
        
        treated = detect_and_treat_anomalies(df, z_threshold=3.0)
        self.assertIn("is_anomaly", treated.columns)
        self.assertTrue(treated.loc[20, "is_anomaly"])
        # The anomaly should be imputed closer to the seasonal expected value
        self.assertLess(treated.loc[20, "kpi_volume_gb"], 15000.0)


class TestTrafficSplit(unittest.TestCase):
    def test_chronological_split_integrity(self):
        dates = pd.date_range("2025-01-01", periods=100, freq="D")
        df = pd.DataFrame({
            "date": dates,
            "kpi_volume_gb": np.random.uniform(1000, 2000, size=100)
        })
        train_df, val_df, test_df = chronological_split(df, train_ratio=0.7, val_ratio=0.15, save_dir=None)

        self.assertEqual(len(train_df), 70)
        self.assertEqual(len(val_df), 15)
        self.assertEqual(len(test_df), 15)
        
        # Verify strict temporal monotonicity
        self.assertLess(train_df["date"].max(), val_df["date"].min())
        self.assertLess(val_df["date"].max(), test_df["date"].min())


class TestTrafficFeatures(unittest.TestCase):
    def test_feature_creation_and_no_lookahead(self):
        dates = pd.date_range("2025-01-01", periods=60, freq="D")
        df = pd.DataFrame({
            "date": dates,
            "kpi_volume_gb": np.arange(100.0, 160.0)
        })
        featured = create_time_features(df, target_col="kpi_volume_gb")
        
        # Verify lag 1 is strictly yesterday's value
        self.assertEqual(featured["lag_1"].iloc[5], featured["kpi_volume_gb"].iloc[4])
        # Verify rolling mean is computed on past values (shift(1))
        # At row 7, rolling_mean_7 should equal mean of rows 0..6
        self.assertAlmostEqual(featured["rolling_mean_7"].iloc[7], featured["kpi_volume_gb"].iloc[:7].mean())
        
        cols = get_feature_columns(featured)
        self.assertNotIn("kpi_volume_gb", cols)
        self.assertNotIn("date", cols)


class TestTrafficModels(unittest.TestCase):
    def test_calculate_metrics(self):
        y_true = np.array([100.0, 200.0, 300.0])
        y_pred = np.array([110.0, 190.0, 300.0])
        metrics = calculate_metrics(y_true, y_pred)
        
        self.assertIn("MAE", metrics)
        self.assertIn("RMSE", metrics)
        self.assertIn("WAPE (%)", metrics)
        self.assertIn("R2", metrics)
        self.assertAlmostEqual(metrics["MAE"], 20.0 / 3.0, places=3)

    def test_seasonal_naive_model(self):
        df = pd.DataFrame({
            "lag_7": [150.0, 160.0, 170.0]
        })
        model = SeasonalNaiveModel(lag=7)
        preds = model.predict(df)
        np.testing.assert_array_equal(preds, np.array([150.0, 160.0, 170.0]))


if __name__ == "__main__":
    unittest.main()
