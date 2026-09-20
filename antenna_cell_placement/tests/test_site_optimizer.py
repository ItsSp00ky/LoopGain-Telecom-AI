import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

from antenna_cell_placement import site_optimizer


class SiteOptimizerTests(unittest.TestCase):
    def optimizer(self):
        optimizer = site_optimizer.CellSiteOptimizer.__new__(site_optimizer.CellSiteOptimizer)
        optimizer.generate_candidate_grid = Mock(return_value=([13.0], [32.0]))
        optimizer.extractor = Mock()
        optimizer.extractor.extract_features.return_value = pd.DataFrame({
            "dist_to_nearest_site_m": [2500.0],
            "population_sum_5km": [1000.0],
            "dist_to_nearest_road_m": [100.0],
        })
        optimizer.suitability_model = Mock()
        optimizer.equipment_model = Mock()
        return optimizer

    def test_no_qualifying_candidates_clears_previous_exports(self):
        optimizer = self.optimizer()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            csv_path = output / 'recommendations.csv'
            geojson_path = output / 'recommended_cell_placements.geojson'
            csv_path.write_text('old recommendations')
            geojson_path.write_text('old recommendations')
            with patch.object(site_optimizer, 'RECOMMENDATIONS_CSV', csv_path), \
                    patch.object(site_optimizer, 'REPORTS_DIR', output), \
                    patch('antenna_cell_placement.opencellid.annotate_candidates', side_effect=lambda df: df):
                result = optimizer.find_optimal_placements(min_gap_distance_m=3000)
            self.assertTrue(result.empty)
            self.assertEqual(list(result.columns), site_optimizer.RECOMMENDATION_COLUMNS)
            self.assertTrue(pd.read_csv(csv_path).empty)
            self.assertEqual(json.loads(geojson_path.read_text())['features'], [])
        optimizer.suitability_model.predict_proba.assert_not_called()
        optimizer.equipment_model.predict.assert_not_called()

    def test_empty_grid_does_not_extract_features(self):
        optimizer = self.optimizer()
        optimizer.generate_candidate_grid.return_value = ([], [])
        with patch.object(site_optimizer, 'export_recommendations', side_effect=lambda df: df):
            self.assertTrue(optimizer.find_optimal_placements().empty)
        optimizer.extractor.extract_features.assert_not_called()

    def test_qualifying_candidate_keeps_its_rank_and_scores(self):
        optimizer = self.optimizer()
        values = dict.fromkeys(site_optimizer.RECOMMENDATION_COLUMNS, 0.0)
        values.update(dict.fromkeys(site_optimizer.SUITABILITY_FEATURE_COLS, 0.0))
        values.update({
            "canonical_longitude": 13.0, "canonical_latitude": 32.0,
            "dist_to_nearest_site_m": 5000.0, "population_sum_5km": 1000.0,
            "dist_to_nearest_road_m": 100.0, "cloudflare_priority_factor": 1.0,
            "dist_to_libyana_site_m": 6000.0, "dist_to_almadar_site_m": 7000.0,
            "utm_x": 1000.0, "utm_y": 2000.0,
        })
        optimizer.extractor.extract_features.return_value = pd.DataFrame([values])
        optimizer.suitability_model.predict_proba.return_value = np.array([[0.2, 0.8]])
        optimizer.equipment_model.predict.return_value = ["Urban_HighCapacity_Macro"]
        with patch.object(site_optimizer, 'export_recommendations', side_effect=lambda df: df):
            result = optimizer.find_optimal_placements(top_k=1)
        self.assertEqual(result.recommendation_rank.tolist(), [1])
        self.assertEqual(result.placement_suitability_score.tolist(), [0.8])
        self.assertEqual(result.deployment_priority_score.tolist(), [2.4])

    def test_invalid_limits_fail_before_generating_candidates(self):
        for kwargs in ({'top_k': 0}, {'top_k': -1}, {'top_k': 1.5},
                       {'min_gap_distance_m': -1}, {'min_population_5km': float('nan')}):
            optimizer = self.optimizer()
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                optimizer.find_optimal_placements(**kwargs)
            optimizer.generate_candidate_grid.assert_not_called()


if __name__ == '__main__':
    unittest.main()
