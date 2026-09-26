"""Integration boundaries: eligibility, missingness, source changes and ML isolation."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

from antenna_cell_placement.gis_v2 import FEATURE_VERSION, GEOD
from antenna_cell_placement.integrated_optimizer import CellSiteOptimizer, PlanningConstraints, select_spatially_separated
from antenna_cell_placement.planning_comparison import compare_rankings
from antenna_cell_placement.planning_features import PlanningFeatureExtractor
from antenna_cell_placement.source_integrity import sha256, verify_sources, require_sources, download_lock


def fixture():
    return pd.DataFrame([dict(
        candidate_id=f'candidate-{i}', candidate_source='fixture', feature_version=FEATURE_VERSION,
        canonical_latitude=32.8, canonical_longitude=13.1 + i * .04,
        inside_libya=True, population_data_available=True, terrain_data_available=True,
        worldcover_data_available=True, worldcover_is_water=False,
        population_sum_5km=10000. + i * 1000, population_valid_fraction_5km=1.,
        dist_to_nearest_site_m=10000., dist_to_nearest_road_m=500.,
        elevation_m=100., elevation_prominence_3km=20., terrain_slope_deg=3.,
        h3_r7='871f89549ffffff', operator_scope='all', building_height_status='Unavailable',
    ) for i in range(4)])


class IntegrationTests(unittest.TestCase):
    def test_ahmed_formula_reproduced_on_corrected_contract(self):
        scored = CellSiteOptimizer.evaluate_features(fixture())
        expected = 100 * (.4 * np.log1p(10000) / np.log1p(100000) + .3 * 7000 / 17000 + .2 * .875 + .1 * .75)
        self.assertAlmostEqual(scored.planning_priority_score.iloc[0], expected, places=4)
        self.assertTrue(scored.eligible.all())

    def test_constraints_reject_missing_water_and_infinite_features(self):
        frame = fixture()
        frame.loc[0, 'population_data_available'] = False
        frame.loc[1, 'worldcover_is_water'] = True
        frame.loc[2, 'dist_to_nearest_road_m'] = np.inf
        frame.loc[3, 'dist_to_nearest_site_m'] = 2999
        scored = CellSiteOptimizer.evaluate_features(frame)
        self.assertFalse(scored.eligible.any())
        self.assertIn('incomplete_population', scored.rejection_reasons.iloc[0])
        self.assertTrue(select_spatially_separated(scored).empty)

    def test_selection_is_geodesic_and_stable_under_input_shuffle(self):
        frame = fixture()
        frame['population_sum_5km'] = 10000
        scored = CellSiteOptimizer.evaluate_features(frame)
        constraints = PlanningConstraints(min_candidate_separation_m=6000)
        selected = select_spatially_separated(scored, constraints)
        other = select_spatially_separated(scored.sample(frac=1, random_state=4), constraints)
        self.assertEqual(selected.candidate_id.tolist(), other.candidate_id.tolist())
        self.assertLess(len(selected), len(scored))
        for a in selected.itertuples():
            for b in selected.itertuples():
                if a.candidate_id != b.candidate_id:
                    self.assertGreaterEqual(GEOD.inv(a.canonical_longitude, a.canonical_latitude, b.canonical_longitude, b.canonical_latitude)[2], 6000)

    def test_rejected_coordinate_reason_never_claims_constraints_pass(self):
        frame = fixture().iloc[:1].copy()
        frame['population_data_available'] = False
        frame['population_sum_5km'] = np.nan
        frame['dist_to_nearest_site_m'] = 100
        result = CellSiteOptimizer.evaluate_features(frame)
        self.assertTrue(result.reason_codes.iloc[0].startswith('ineligible;'))
        self.assertIn('incomplete_population', result.reason_codes.iloc[0])
        self.assertNotIn('meets_minimum_planning_constraints', result.reason_codes.iloc[0])

    def test_version_and_invalid_constraint_fail_explicitly(self):
        frame = fixture()
        frame['feature_version'] = 'legacy'
        with self.assertRaises(ValueError):
            CellSiteOptimizer.evaluate_features(frame)
        for kwargs in ({'top_k': 0}, {'min_gap_distance_m': -1}, {'max_road_distance_m': np.nan}):
            with self.assertRaises(ValueError):
                PlanningConstraints(**kwargs)

    def test_assess_handles_missing_optional_osm_without_int_na(self):
        from antenna_cell_placement.placement import assess_coordinate
        extractor = PlanningFeatureExtractor.__new__(PlanningFeatureExtractor)
        extractor.verification = {'sources': []}
        optimizer = CellSiteOptimizer(extractor=extractor)
        optimizer.evaluate_coordinates = Mock(return_value=CellSiteOptimizer.evaluate_features(fixture().iloc[:1]))
        with patch('antenna_cell_placement.placement.CellSiteOptimizer', return_value=optimizer):
            result = assess_coordinate(32.8, 13.1)
        self.assertIsNone(result['osm_hospital_count_h3'])
        self.assertFalse(result['osm_selected_context_available'])

    def test_batch_and_coordinate_assessment_share_the_same_score(self):
        extractor = Mock()
        extractor.extract.return_value = fixture().iloc[:1].drop(columns=['candidate_id', 'candidate_source'])
        optimizer = CellSiteOptimizer(extractor=extractor)
        single = optimizer.evaluate_coordinates([13.1], [32.8])
        batch = optimizer.evaluate_features(fixture().iloc[:1])
        self.assertEqual(single.planning_priority_score.iloc[0], batch.planning_priority_score.iloc[0])
        self.assertEqual(single.eligible.iloc[0], batch.eligible.iloc[0])

    def test_matched_baselines_cannot_select_rejected_candidates(self):
        frame = fixture()
        frame.loc[0, 'worldcover_is_water'] = True
        pool = CellSiteOptimizer.evaluate_features(frame)
        original = pool.copy(deep=True)
        _, report = compare_rankings(pool, PlanningConstraints())
        pd.testing.assert_frame_equal(pool, original)
        for result in report['comparisons'].values():
            self.assertNotIn('candidate-0', result['selected_candidate_ids'])
        self.assertEqual(report['eligible_count'], 3)

    def test_empty_candidate_selection_and_comparison_are_valid(self):
        pool = CellSiteOptimizer.evaluate_features(fixture().iloc[:0])
        _, report = compare_rankings(pool, PlanningConstraints())
        self.assertEqual(report['selected_count'], 0)
        self.assertIsNone(report['comparisons']['population_only']['overlap_with_explainable'])

    def test_public_import_does_not_load_ml_modules(self):
        code = 'import sys; import antenna_cell_placement.planning_pipeline; assert not any(n in sys.modules for n in ["lightgbm", "sklearn", "joblib", "antenna_cell_placement.placement_model"])'
        subprocess.run([sys.executable, '-c', code], check=True, capture_output=True, text=True)


class IntegrityTests(unittest.TestCase):
    def test_changed_required_and_missing_optional_are_distinguished(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'source.bin'
            source.write_bytes(b'reviewed')
            lock = root / 'lock.json'
            lock.write_text(json.dumps({'sources': [
                {'path': 'source.bin', 'sha256': sha256(source), 'required': True, 'group': 'core'},
                {'path': 'optional.bin', 'sha256': '0' * 64, 'required': False, 'group': 'osm'},
            ]}))
            report = verify_sources(root, lock)
            require_sources(report)
            self.assertEqual(report['sources'][1]['status'], 'missing')
            source.write_bytes(b'changed!')
            with self.assertRaises(ValueError):
                require_sources(verify_sources(root, lock))

    def test_source_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            lock = root / 'lock.json'
            lock.write_text(json.dumps({'sources': [{'path': '../escape', 'required': True}]}))
            with self.assertRaises(ValueError):
                verify_sources(root, lock)

    def test_portable_download_lock_is_exclusive_and_released(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '.lock'
            with download_lock(path):
                with self.assertRaises(RuntimeError):
                    with download_lock(path):
                        pass
            self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
