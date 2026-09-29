"""Same-candidate rankings. Overlap and sensitivity are not outcome validation."""
import numpy as np
from antenna_cell_placement.integrated_optimizer import select_spatially_separated
from antenna_cell_placement.planning_score import SCORE_COMPONENT_COLUMNS


def compare_rankings(pool, constraints, experimental_model=None):
    pool = pool.copy()
    eligible = pool.loc[pool.eligible].copy()
    primary = select_spatially_separated(pool, constraints)
    ids = set(primary.candidate_id)
    report = {
        'candidate_count': len(pool), 'eligible_count': len(eligible),
        'selected_count': len(primary),
        'interpretation': 'Matched candidates and constraints; overlap measures ranking differences, not RF benefit. No outcome labels are available.',
        'comparisons': {}, 'weight_sensitivity': [],
    }
    scores = {
        'population_only': 'population_sum_5km',
        'gap_only': 'dist_to_nearest_site_m',
        'explainable': 'planning_priority_score',
    }
    if experimental_model is not None:
        if 'operator_scope' not in pool or not pool.operator_scope.eq('all').all():
            raise ValueError('The current research model requires all-network features; operator-specific comparisons need a matching trained artifact')
        import joblib
        model = joblib.load(experimental_model)
        from antenna_cell_placement.gis_v2 import FEATURE_VERSION
        if getattr(model, 'feature_version', None) != FEATURE_VERSION:
            raise ValueError('Comparison requires an explicitly versioned GIS-v2 model')
        pool['experimental_site_pattern_score'] = model.predict_proba(pool)[:, 1]
        pool['experimental_combined_score'] = pool.planning_priority_score * (.75 + .5 * pool.experimental_site_pattern_score)
        scores.update(ml_only='experimental_site_pattern_score', experimental_combination='experimental_combined_score')
        eligible = pool.loc[pool.eligible].copy()
        report['model_inventory_note'] = 'Historical GIS-v2 model evaluated on the current inventory snapshot; no retraining or transfer-accuracy claim. Historical AUC does not describe this run.'
        report['ml_interpretation'] = 'Existing-site pattern recognition, not a deployment-success probability. Combination multiplier is an unvalidated research assumption; primary rank is unchanged.'
    for name, column in scores.items():
        selected = select_spatially_separated(pool, constraints, column)
        report['comparisons'][name] = {
            'selected_candidate_ids': selected.candidate_id.tolist(),
            'overlap_with_explainable': len(ids & set(selected.candidate_id)) / len(ids) if ids else None,
            'spearman_with_explainable': _correlation(eligible[column], eligible.planning_priority_score),
        }
        order = eligible.sort_values([column, 'candidate_id'], ascending=[False, True]).index
        pool[name + '_rank'] = np.nan
        pool.loc[order, name + '_rank'] = np.arange(1, len(order) + 1)
    weights = np.array([.4, .3, .2, .1])
    for index, component in enumerate(SCORE_COMPONENT_COLUMNS):
        for factor in (.5, 1.5):
            changed = weights.copy()
            changed[index] *= factor
            changed /= changed.sum()
            pool['sensitivity_score'] = 100 * (pool[SCORE_COMPONENT_COLUMNS].to_numpy() @ changed)
            selected = select_spatially_separated(pool, constraints, 'sensitivity_score')
            report['weight_sensitivity'].append({
                'component': component, 'factor': factor,
                'shortlist_overlap': len(ids & set(selected.candidate_id)) / len(ids) if ids else None,
                'spearman': _correlation(pool.loc[pool.eligible, 'sensitivity_score'], eligible.planning_priority_score),
            })
    from dataclasses import replace
    from antenna_cell_placement.integrated_optimizer import CellSiteOptimizer
    report['cutoff_sensitivity'] = []
    for name in ('min_gap_distance_m', 'min_population_5km', 'max_road_distance_m', 'min_candidate_separation_m'):
        for factor in (.5, 1.5):
            changed = replace(constraints, **{name: getattr(constraints, name) * factor})
            evaluated = CellSiteOptimizer.evaluate_features(pool, changed)
            selected = select_spatially_separated(evaluated, changed)
            report['cutoff_sensitivity'].append({
                'constraint': name, 'factor': factor, 'eligible_count': int(evaluated.eligible.sum()),
                'selected_count': len(selected),
                'overlap_with_default': len(ids & set(selected.candidate_id)) / len(ids) if ids else None,
            })
    report['missing_data_stress'] = []
    for flag, field in [('population_data_available', 'population_sum_5km'), ('terrain_data_available', 'elevation_m'), ('worldcover_data_available', None)]:
        stressed = pool.copy()
        # Fixed IDs select a repeatable 10% subset; never alters the source pool.
        missing = stressed.sort_values('candidate_id').iloc[::10].index
        stressed.loc[missing, flag] = False
        if field:
            stressed.loc[missing, field] = np.nan
        evaluated = CellSiteOptimizer.evaluate_features(stressed, constraints)
        selected = select_spatially_separated(evaluated, constraints)
        report['missing_data_stress'].append({
            'removed_evidence': flag, 'affected_candidates': len(missing),
            'eligible_count': int(evaluated.eligible.sum()), 'selected_count': len(selected),
            'affected_candidates_selected': int(selected.candidate_id.isin(stressed.loc[missing, 'candidate_id']).sum()),
        })
    return pool.drop(columns='sensitivity_score'), report


def _correlation(a, b):
    if len(a) < 2 or a.nunique() < 2 or b.nunique() < 2:
        return None
    value = a.corr(b, method='spearman')
    return float(value) if np.isfinite(value) else None
