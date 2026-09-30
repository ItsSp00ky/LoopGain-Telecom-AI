"""Tests for the all-KPI exogenous feature set and its leakage guard."""

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

_PKG_ROOT = Path(__file__).resolve().parent.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from src.feature_engineering import aggregate_carrier_kpis_daily, prepare_multivariate_datasets
from src.model_definitions import forecast_future

RAW_MACRO_COLUMNS = {
    "RRC Setup Success Rate", "E-RAB Establishment Success Rate", "E-RAB Drop Rate",
    "Handover Success Rate ( 4G Intra System)", "Handover Success Rate",
    "E-UTRAN IP Throughput UE DL", "E-UTRAN IP Throughput UE UL",
}


class CarrierAggregationTests(unittest.TestCase):
    def test_one_row_per_day_as_a_plain_band_mean(self):
        frame = pd.DataFrame({
            "Date": ["2026-01-01", "2026-01-01", "2026-01-02"],
            "earfcndl": [350, 1700, 350],
            "4G Cell Av. (%)": [90.0, 100.0, 80.0],
            "Avg RRC Connected users": [10.0, 30.0, 5.0],
            "pmCellDowntimeMan": [0.0, 200.0, 50.0],
        })
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "carrier.csv"
            frame.to_csv(path, index=False)
            daily = aggregate_carrier_kpis_daily(path)
        self.assertEqual(len(daily), 2)
        first = daily.iloc[0]
        self.assertAlmostEqual(first["network_availability_pct"], 95.0)
        self.assertAlmostEqual(first["network_avg_connected_users"], 20.0)
        self.assertAlmostEqual(first["network_cell_downtime_raw"], 100.0)


class EnrichedDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.datasets, _, cls.features = prepare_multivariate_datasets()

    def test_no_raw_same_day_kpi_ever_reaches_the_model(self):
        raw = RAW_MACRO_COLUMNS | set(self.datasets["exo_cols"])
        self.assertEqual(sorted(raw & set(self.features)), [])

    def test_every_available_kpi_is_an_exogenous_feature(self):
        for kpi in [
            "macro_erab_estab_sr", "macro_handover_sr_intra4g",
            "network_availability_pct", "network_avg_connected_users", "network_cell_downtime_raw",
        ]:
            self.assertIn(f"exo_{kpi}_lag1", self.features)
            self.assertIn(f"exo_{kpi}_roll7", self.features)

    def test_exogenous_features_are_yesterdays_values(self):
        full = self.datasets["full_df"]
        c = "network_availability_pct"
        np.testing.assert_allclose(full[f"exo_{c}_lag1"].iloc[1:].values, full[c].iloc[:-1].values)

    def test_exo_subset_restricts_features_on_identical_rows(self):
        subset, _, features = prepare_multivariate_datasets(exo_subset=["macro_dl_throughput_mbps"])
        self.assertEqual(subset["exo_cols"], ["macro_dl_throughput_mbps"])
        self.assertFalse(any(f.startswith("exo_network_") for f in features))
        self.assertEqual(len(subset["full_df"]), len(self.datasets["full_df"]))


class ExogenousForecastTests(unittest.TestCase):
    def test_future_kpis_are_carried_forward_from_the_last_real_value(self):
        datasets, _, features = prepare_multivariate_datasets()

        class Echo:
            """Returns the carried exogenous roll7 so the test can see what was fed in."""
            def predict(self, X):
                return X["exo_network_availability_pct_roll7"].values

        full = datasets["full_df"]
        forecast = forecast_future(Echo(), full, features, horizon_days=10, exo_cols=datasets["exo_cols"])
        last_real = full["network_availability_pct"].iloc[-1]
        # After 7 carried days the rolling window holds only the carried value.
        self.assertAlmostEqual(forecast["predicted_kpi_volume_gb"].iloc[-1], last_real)


if __name__ == "__main__":
    unittest.main()
