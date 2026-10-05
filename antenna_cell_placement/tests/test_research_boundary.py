import unittest
from unittest.mock import Mock, patch
import numpy as np
import pandas as pd

from test_integrated_planning import fixture
from antenna_cell_placement.gis_v2 import FEATURE_VERSION
from antenna_cell_placement.integrated_optimizer import CellSiteOptimizer, PlanningConstraints, select_spatially_separated
from antenna_cell_placement.planning_comparison import compare_rankings


class ResearchBoundaryTests(unittest.TestCase):
    def test_optional_ml_does_not_change_primary_scores_or_selected_ids(self):
        pool = CellSiteOptimizer.evaluate_features(fixture())
        original = pool.copy(deep=True)
        model = Mock(feature_version=FEATURE_VERSION)
        model.predict_proba.return_value = np.array([[.1,.9],[.9,.1],[.7,.3],[.2,.8]])
        with patch('joblib.load', return_value=model):
            compared, report = compare_rankings(pool, PlanningConstraints(), 'trusted_fixture.joblib')
        pd.testing.assert_frame_equal(pool, original)
        pd.testing.assert_series_equal(compared.planning_priority_score, original.planning_priority_score)
        self.assertEqual(select_spatially_separated(compared).candidate_id.tolist(), select_spatially_separated(original).candidate_id.tolist())
        self.assertIn('ml_only', report['comparisons'])

    def test_wrong_model_and_operator_contract_are_rejected(self):
        pool = CellSiteOptimizer.evaluate_features(fixture())
        with patch('joblib.load', return_value=Mock(feature_version='legacy')):
            with self.assertRaises(ValueError):
                compare_rankings(pool, PlanningConstraints(), 'legacy.joblib')
        pool['operator_scope'] = 'almadar'
        with self.assertRaises(ValueError):
            compare_rankings(pool, PlanningConstraints(), 'all_network_model.joblib')
