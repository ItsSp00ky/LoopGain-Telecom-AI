"""Grid sensitivity and inventory-hidden recovery; diagnostic, never RF truth.

Run against a completed all-network Tripoli run. The primary shortlist is read
only. Every network feature is rebuilt after hiding sites in each fold.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

import h3
import numpy as np
import pandas as pd
from scipy.stats import rankdata

from antenna_cell_placement.config import CLEANED_PHYSICAL_SITES_CSV
from antenna_cell_placement.gis_v2 import GEOD, network_features
from antenna_cell_placement.integrated_optimizer import CellSiteOptimizer, PlanningConstraints, select_spatially_separated
from antenna_cell_placement.source_integrity import sha256


def auc(labels, scores):
    labels, scores = np.asarray(labels, dtype=bool), np.asarray(scores, dtype=float)
    keep = np.isfinite(scores)
    labels, scores = labels[keep], scores[keep]
    positives, negatives = int(labels.sum()), int((~labels).sum())
    if not positives or not negatives:
        return None
    ranks = rankdata(scores)
    return float((ranks[labels].sum() - positives * (positives + 1) / 2) / (positives * negatives))


def validate(run):
    run = Path(run)
    manifest = json.loads((run / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['status'] != 'completed' or manifest['operator_scope'] != 'all' or manifest['scope'] != 'Tripoli':
        raise ValueError('This diagnostic requires a completed all-network Tripoli run')
    path = run / 'comparison_candidates.parquet'
    if sha256(path) != manifest['artifacts'][path.name]:
        raise ValueError('Candidate artifact changed')
    pool = pd.read_parquet(path)
    constraints = PlanningConstraints(**manifest['constraints'])
    original = select_spatially_separated(pool, constraints)
    output = run / 'sensitivity'
    output.mkdir(exist_ok=False)
    optimizer = CellSiteOptimizer()
    if optimizer.extractor.verification['source_lock_sha256'] != manifest['sources']['source_lock_sha256']:
        raise ValueError('Grid comparison requires the same reviewed sources')
    resolution = max(6, manifest['h3_resolution'] - 1)
    alternate = optimizer.build_candidate_pool('Tripoli', resolution, constraints)
    selected = select_spatially_separated(alternate, constraints)
    alternate.to_csv(output / f'candidates_r{resolution}.csv', index=False)
    selected.to_csv(output / f'shortlist_r{resolution}.csv', index=False)
    nearest = []
    for row in selected.itertuples():
        distances = GEOD.inv(np.full(len(original), row.canonical_longitude), np.full(len(original), row.canonical_latitude), original.canonical_longitude.to_numpy(), original.canonical_latitude.to_numpy())[2]
        if len(distances):
            nearest.append(float(np.min(distances)))
    grid_report = {
        'baseline_resolution': manifest['h3_resolution'], 'alternate_resolution': resolution,
        'baseline_candidate_count': len(pool), 'alternate_candidate_count': len(alternate),
        'baseline_eligible_count': int(pool.eligible.sum()), 'alternate_eligible_count': int(alternate.eligible.sum()),
        'baseline_selected_count': len(original), 'alternate_selected_count': len(selected),
        'alternate_selections_within_2500m_of_baseline': sum(d <= 2500 for d in nearest),
        'median_nearest_baseline_distance_m': float(np.median(nearest)) if nearest else None,
        'interpretation': 'Grid centres change with resolution. This is spatial proximity of independently ranked shortlists, not candidate-ID overlap or RF validation.',
    }

    sites = pd.read_csv(CLEANED_PHYSICAL_SITES_CSV)
    cells = [h3.latlng_to_cell(r.canonical_latitude, r.canonical_longitude, manifest['h3_resolution']) for r in sites.itertuples()]
    site_cells = pd.Series(cells, index=sites.index)
    pilot_sites = sites.index[site_cells.isin(set(pool.h3_index))].to_numpy()
    folds = []
    for seed in range(5):
        hidden_index = np.random.default_rng(20260923 + seed).choice(pilot_sites, max(1, int(.2 * len(pilot_sites))), replace=False)
        hidden = sites.loc[hidden_index]
        kept = sites.drop(index=hidden_index).reset_index(drop=True)
        assert not set(hidden.physical_site_id).intersection(set(kept.physical_site_id))
        rebuilt = pd.DataFrame([network_features(r.canonical_longitude, r.canonical_latitude, kept) for r in pool.itertuples()])
        treatment = pool.copy()
        for col in rebuilt:
            treatment[col] = rebuilt[col].to_numpy()
        evaluated = CellSiteOptimizer.evaluate_features(treatment, constraints)
        labels = pool.h3_index.isin(set(site_cells.loc[hidden_index])).to_numpy()
        scorable = (np.isfinite(evaluated.planning_priority_score) & evaluated.population_data_available
                    & evaluated.terrain_data_available & evaluated.worldcover_data_available
                    & ~evaluated.worldcover_is_water).to_numpy()
        selected_hidden = select_spatially_separated(evaluated, constraints)
        folds.append({
            'seed': 20260923 + seed, 'hidden_site_ids': hidden.physical_site_id.astype(int).tolist(),
            'kept_site_count': len(kept), 'hidden_site_count': len(hidden),
            'rebuilt_network_fields': list(rebuilt.columns),
            'scorable_candidates': int(scorable.sum()), 'positive_scorable_hexes': int(labels[scorable].sum()),
            'planning_auc': auc(labels[scorable], evaluated.loc[scorable, 'planning_priority_score']),
            'population_auc': auc(labels[scorable], evaluated.loc[scorable, 'population_sum_5km']),
            'eligible_count': int(evaluated.eligible.sum()), 'selected_count': len(selected_hidden),
            'hidden_site_hexes_in_selected': int(selected_hidden.h3_index.isin(set(site_cells.loc[hidden_index])).sum()),
        })
    recovery = {
        'folds': folds, 'pilot_existing_sites': len(pilot_sites),
        'mean_planning_auc': float(np.mean([f['planning_auc'] for f in folds if f['planning_auc'] is not None])),
        'mean_population_auc': float(np.mean([f['population_auc'] for f in folds if f['population_auc'] is not None])),
        'interpretation': 'Historical-site recovery on the already inspected Tripoli domain. Hidden sites were removed from every network distance/density feature before scoring. Population/terrain/roads are independent of inventory. Labels indicate a hidden site somewhere in the candidate H3 cell, not verified coverage need. No independent deployment labels or blind test are claimed.',
    }
    report = {'candidate_sha256': sha256(path), 'source_lock_sha256': manifest['sources']['source_lock_sha256'],
              'tool_sha256': sha256(Path(__file__)), 'constraints': asdict(constraints),
              'grid_resolution': grid_report, 'hidden_site_recovery': recovery}
    (output / 'diagnostics.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'grid_resolution': grid_report, 'mean_planning_auc': recovery['mean_planning_auc'], 'mean_population_auc': recovery['mean_population_auc']}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    validate(parser.parse_args().run)
