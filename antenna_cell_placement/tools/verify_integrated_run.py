"""Verify real exports and coordinate/batch agreement against the run manifest."""
import argparse
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point

from antenna_cell_placement.gis_v2 import GEOD
from antenna_cell_placement.integrated_optimizer import CellSiteOptimizer, PlanningConstraints
from antenna_cell_placement.planning_features import PlanningFeatureExtractor
from antenna_cell_placement.source_integrity import sha256, verify_sources


def verify(run):
    run = Path(run)
    manifest = json.loads((run / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['status'] == 'completed'
    for relative, expected in manifest['artifacts'].items():
        assert sha256(run / relative) == expected, relative
    pool = pd.read_csv(run / 'candidates.csv')
    shortlist = pd.read_csv(run / 'shortlist.csv')
    constraints = PlanningConstraints(**manifest['constraints'])
    assert shortlist.eligible.all()
    assert set(shortlist.candidate_id).issubset(set(pool.loc[pool.eligible, 'candidate_id']))
    assert not any(c.startswith('recommended_') for c in shortlist)
    assert not any('experimental_' in c for c in shortlist)
    for i, a in enumerate(shortlist.itertuples()):
        for b in list(shortlist.itertuples())[i+1:]:
            assert GEOD.inv(a.canonical_longitude, a.canonical_latitude, b.canonical_longitude, b.canonical_latitude)[2] >= constraints.min_candidate_separation_m
    verification = verify_sources()
    # Exercise the actual assessment implementation with optional OSM disabled,
    # without renaming or modifying any data file on disk.
    for source in verification['sources']:
        if source['group'] == 'osm':
            source['status'] = 'missing'
    verification['metadata_checks']['osm']['verified'] = False
    extractor = PlanningFeatureExtractor(manifest['operator_scope'], verification)
    optimizer = CellSiteOptimizer(extractor=extractor)
    row = shortlist.iloc[0]
    assessed = optimizer.evaluate_coordinates([row.canonical_longitude], [row.canonical_latitude], constraints)
    context = extractor.add_context(assessed)
    assert abs(assessed.planning_priority_score.iloc[0] - row.planning_priority_score) < 1e-4
    assert bool(assessed.eligible.iloc[0])
    assert pd.isna(context.osm_hospital_count_h3.iloc[0])
    assert not context.osm_selected_context_available.iloc[0]
    from unittest.mock import patch
    from antenna_cell_placement.placement import assess_coordinate
    with patch('antenna_cell_placement.placement.CellSiteOptimizer', return_value=optimizer):
        assessment = assess_coordinate(row.canonical_latitude, row.canonical_longitude, constraints=constraints)
    assert assessment['osm_hospital_count_h3'] is None
    heights = 0
    roofs_path = run / 'rooftop_candidates.geojson'
    if roofs_path.exists():
        roofs = gpd.read_file(roofs_path)
        if len(roofs):
            assert set(roofs.h3_index).issubset(set(shortlist.h3_index))
            assert all(geometry.covers(Point(lon, lat)) for geometry, lon, lat in zip(roofs.geometry, roofs.canonical_longitude, roofs.canonical_latitude))
            heights = int(roofs.building_height_known.sum())
            assert heights == 0
    inventory = json.loads((run / 'inventory_audit.json').read_text())
    assert inventory['owner_confirmed_almadar_records'] == 645
    assert inventory['owner_attribution_correct']
    crosswalk = pd.read_csv(run / 'source_crosswalk.csv')
    owner = crosswalk.loc[crosswalk.owner_confirmed_almadar.fillna(False)]
    assert len(owner) == 645
    assert owner.loc[owner.status.eq('retained'), 'operator'].eq('Al-Madar').all()
    assert inventory['clusters_with_diameter_over_50m'] == 0
    report = {'artifact_hashes_match': True, 'strict_constraints_hold': True,
              'batch_assess_score_matches': True, 'missing_optional_osm_assess_passed': True,
              'primary_has_no_ml_columns': True, 'footprint_coordinates_inside_geometry': True,
              'known_footprint_heights': heights, 'owner_confirmed_almadar_records': 645,
              'candidate_count': len(pool), 'eligible_count': int(pool.eligible.sum()),
              'shortlist_count': len(shortlist)}
    (run / 'integration_verification.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    verify(parser.parse_args().run)
