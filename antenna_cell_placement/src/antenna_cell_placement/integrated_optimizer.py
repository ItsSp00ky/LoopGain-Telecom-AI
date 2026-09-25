"""Integrated public planner. No learned model participates in primary ranking."""
from dataclasses import asdict, dataclass
import numpy as np
import pandas as pd

from antenna_cell_placement.gis_v2 import GEOD, FEATURE_VERSION
from antenna_cell_placement.planning_score import (
    SCORE_VERSION, SCORE_COMPONENT_COLUMNS, REQUIRED_CANDIDATE_FIELDS,
    score_candidate_features, candidate_id, add_reason_codes, eligible_candidate_mask,
)


@dataclass(frozen=True)
class PlanningConstraints:
    min_gap_distance_m: float = 3000.
    min_population_5km: float = 300.
    max_road_distance_m: float = 4000.
    min_candidate_separation_m: float = 2500.
    top_k: int = 20

    def __post_init__(self):
        if isinstance(self.top_k, bool) or not isinstance(self.top_k, int) or self.top_k < 1:
            raise ValueError('top_k must be a positive integer')
        for key, value in asdict(self).items():
            if key != 'top_k' and (not np.isfinite(value) or value < 0):
                raise ValueError(f'{key} must be finite and nonnegative')


def evaluate_eligibility(features, constraints=PlanningConstraints()):
    """Retain rejected candidates and every applicable rejection reason."""
    result = features.copy()
    if 'feature_version' not in result or not result.feature_version.eq(FEATURE_VERSION).all():
        raise ValueError(f'Public planning requires {FEATURE_VERSION}')
    reasons = [[] for _ in range(len(result))]
    def reject(mask, code):
        for idx in np.flatnonzero(np.asarray(mask, dtype=bool)):
            reasons[idx].append(code)
    for field, reason in (
        ('inside_libya', 'outside_libya'),
        ('population_data_available', 'incomplete_population'),
        ('terrain_data_available', 'incomplete_terrain'),
        ('worldcover_data_available', 'missing_landcover'),
    ):
        reject(~result[field].fillna(False).astype(bool), reason)
    reject(result.worldcover_is_water.fillna(False).astype(bool), 'observed_water')
    for field in REQUIRED_CANDIDATE_FIELDS:
        reject(~np.isfinite(result[field].to_numpy(dtype=float)), 'missing_' + field)
    reject(result.population_sum_5km.lt(constraints.min_population_5km), 'below_population_threshold')
    reject(result.dist_to_nearest_site_m.lt(constraints.min_gap_distance_m), 'too_close_to_known_site')
    reject(result.dist_to_nearest_road_m.gt(constraints.max_road_distance_m), 'too_far_from_road')
    for field in ('population_sum_5km', 'dist_to_nearest_site_m', 'dist_to_nearest_road_m', 'terrain_slope_deg'):
        reject(result[field].lt(0), 'invalid_' + field)
    result['rejection_reasons'] = [';'.join(codes) for codes in reasons]
    result['eligible'] = [not codes for codes in reasons]
    return result


def select_spatially_separated(candidates, constraints=PlanningConstraints(), score_column='planning_priority_score'):
    """Greedy, stable selection using ellipsoidal distances, with no relaxation."""
    if candidates.candidate_id.duplicated().any():
        raise ValueError('Candidate IDs must be unique')
    ranked = candidates.loc[candidates.eligible & np.isfinite(candidates[score_column])].sort_values(
        [score_column, 'candidate_id'], ascending=[False, True], kind='stable')
    indices, selected = [], []
    for index, row in ranked.iterrows():
        lon, lat = row.canonical_longitude, row.canonical_latitude
        if all(GEOD.inv(lon, lat, x, y)[2] >= constraints.min_candidate_separation_m for x, y in selected):
            indices.append(index)
            selected.append((lon, lat))
            if len(indices) >= constraints.top_k:
                break
    result = ranked.loc[indices].reset_index(drop=True)
    result['recommendation_rank'] = np.arange(1, len(result) + 1)
    return result


class CellSiteOptimizer:
    def __init__(self, extractor=None, operator='all', verification=None):
        if extractor is None:
            from antenna_cell_placement.planning_features import PlanningFeatureExtractor
            extractor = PlanningFeatureExtractor(operator, verification)
        self.extractor = extractor

    def evaluate_coordinates(self, lons, lats, constraints=PlanningConstraints(), source='coordinate_review'):
        result = self.extractor.extract(lons, lats)
        result['candidate_source'] = source
        result['candidate_id'] = result.apply(candidate_id, axis=1)
        return self.evaluate_features(result, constraints)

    @staticmethod
    def evaluate_features(features, constraints=PlanningConstraints()):
        result = evaluate_eligibility(features, constraints)
        result = score_candidate_features(result)
        result = add_reason_codes(result)
        result['candidate_status'] = np.where(result.eligible, 'engineering_review', 'ineligible')
        return result

    def build_candidate_pool(self, scope='Tripoli', resolution=8, constraints=PlanningConstraints()):
        from antenna_cell_placement.planning_candidates import generate_candidates
        coordinates = generate_candidates(self.extractor, scope, resolution)
        if coordinates.empty:
            raise ValueError('No candidate coordinates were generated for this scope')
        result = self.extractor.extract(coordinates.canonical_longitude, coordinates.canonical_latitude)
        result['candidate_source'] = coordinates.candidate_source.to_numpy()
        result['candidate_id'] = coordinates.candidate_id.to_numpy()
        import h3
        result['h3_index'] = [h3.latlng_to_cell(lat, lon, resolution) for lon, lat in zip(result.canonical_longitude, result.canonical_latitude)]
        result['h3_resolution'] = resolution
        return self.evaluate_features(result, constraints)

    def find_priority_placements(self, candidates, constraints=PlanningConstraints(), context=True):
        pool = self.evaluate_features(candidates, constraints)
        result = select_spatially_separated(pool, constraints)
        if context:
            result = self.extractor.add_context(result)
            result = add_reason_codes(result)
        return result
