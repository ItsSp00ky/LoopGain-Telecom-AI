"""
tests/test_plots.py
Unit tests for src/plots.py (Single KPI plots, Carrier grid dashboards, and Multiband overlays).
"""

import os
import sys
import unittest
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.config import KPI_KEYS
from src.plots import plot_single_kpi, plot_carrier_grid, plot_multiband_kpi


class TestPlots(unittest.TestCase):
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
        plt.close(fig)

    def test_carrier_grid_plot(self):
        fig = plot_carrier_grid(350, self.hist_df, self.fc_df, dpi=100)
        self.assertIsNotNone(fig)
        plt.close(fig)

    def test_multiband_plot(self):
        fig = plot_multiband_kpi('rrc_setup_sr', self.hist_df, self.fc_df, dpi=100)
        self.assertIsNotNone(fig)
        plt.close(fig)


if __name__ == '__main__':
    unittest.main()
