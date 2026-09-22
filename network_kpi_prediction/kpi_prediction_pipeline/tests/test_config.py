"""
tests/test_config.py
Unit tests for src/config.py (KPI completeness, physical domain bounds, SLA compliance).
"""

import os
import sys
import unittest
import numpy as np

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.config import KPI_CONFIG, KPI_KEYS, apply_bounds, check_sla_compliance


class TestConfig(unittest.TestCase):
    def test_kpi_completeness(self):
        self.assertEqual(len(KPI_KEYS), 10)
        for kpi in KPI_KEYS:
            self.assertIn('name', KPI_CONFIG[kpi])
            self.assertIn('unit', KPI_CONFIG[kpi])
            self.assertIn('category', KPI_CONFIG[kpi])

    def test_apply_bounds(self):
        clipped = apply_bounds(np.array([-5.0, 50.0, 105.0]), 'rrc_setup_sr')
        np.testing.assert_array_equal(clipped, np.array([0.0, 50.0, 100.0]))

        clipped_ratio = apply_bounds(np.array([-0.2, 0.95, 1.5]), 'handover_intra_sr')
        np.testing.assert_array_equal(clipped_ratio, np.array([0.0, 0.95, 1.0]))

        clipped_down = apply_bounds(np.array([-10.0, 500.0]), 'downtime_sec')
        np.testing.assert_array_equal(clipped_down, np.array([0.0, 500.0]))

    def test_sla_compliance(self):
        self.assertTrue(check_sla_compliance(99.5, 'rrc_setup_sr'))
        self.assertFalse(check_sla_compliance(98.5, 'rrc_setup_sr'))
        self.assertTrue(check_sla_compliance(0.2, 'erab_drop_rate'))
        self.assertFalse(check_sla_compliance(0.8, 'erab_drop_rate'))


if __name__ == '__main__':
    unittest.main()
