"""
tests/test_export.py
Unit tests for src/export.py (Untruncated markdown reports, O-RAN RFC 8259 JSON feeds).
"""

import os
import sys
import unittest
import json
import numpy as np
import pandas as pd

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.report_export import build_carrier_markdown_report, build_carrier_json_payload


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


if __name__ == '__main__':
    unittest.main()
