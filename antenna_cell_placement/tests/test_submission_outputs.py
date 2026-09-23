"""Public export regressions: no unsupported advice or relaxed constraints."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import numpy as np
import pandas as pd
from antenna_cell_placement.placement_model import SUITABILITY_FEATURE_COLS
from antenna_cell_placement.site_optimizer import CellSiteOptimizer


class SubmissionOutputTests(unittest.TestCase):
    def run_export(self, gap):
        row = {column: 1.0 for column in SUITABILITY_FEATURE_COLS}
        row.update(canonical_longitude=13.2, canonical_latitude=32.85,
                   municipality_name='Tripoli', nearest_settlement_name='Tripoli',
                   population_sum_5km=12000., dist_to_nearest_site_m=gap,
                   dist_to_nearest_road_m=200., elevation_m=15., utm_x=500., utm_y=600.,
                   cloudflare_regional_demand_score=.5, cloudflare_priority_factor=1.,
                   cloudflare_http_requests_share_52w_pct=1.,
                   cloudflare_annual_traffic_growth_52w_pct=0., cloudflare_data_available=True)
        optimizer = CellSiteOptimizer.__new__(CellSiteOptimizer)
        optimizer.extractor = Mock()
        optimizer.extractor.extract_features.return_value = pd.DataFrame([row])
        optimizer.generate_candidate_grid = Mock(return_value=([13.2], [32.85]))
        optimizer.suitability_model = Mock()
        optimizer.suitability_model.predict_proba.return_value = np.array([[.2,.8]])
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            with patch('antenna_cell_placement.site_optimizer.RECOMMENDATIONS_CSV', directory/'recommendations.csv'), patch('antenna_cell_placement.site_optimizer.REPORTS_DIR', directory), patch('antenna_cell_placement.opencellid.annotate_candidates', side_effect=lambda frame: frame):
                result = optimizer.find_optimal_placements()
            csv = pd.read_csv(directory/'recommendations.csv')
            geojson = json.loads((directory/'recommended_cell_placements.geojson').read_text())
        return optimizer, result, csv, geojson

    def test_exports_contain_no_unsupported_deployment_advice(self):
        _, result, csv, geojson = self.run_export(9000.)
        self.assertEqual(len(result), 1)
        for columns in (result.columns, csv.columns, geojson['features'][0]['properties']):
            self.assertFalse(any(name.startswith('recommended_') for name in columns))
        self.assertAlmostEqual(result.placement_suitability_score.iloc[0], .8)

    def test_no_eligible_candidates_does_not_relax_constraints_or_predict(self):
        optimizer, result, csv, geojson = self.run_export(2500.)
        self.assertTrue(result.empty)
        self.assertTrue(csv.empty)
        self.assertEqual(geojson['features'], [])
        optimizer.suitability_model.predict_proba.assert_not_called()


if __name__ == '__main__':
    unittest.main()
