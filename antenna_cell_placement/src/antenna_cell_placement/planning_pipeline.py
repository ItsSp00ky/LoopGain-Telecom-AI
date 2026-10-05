"""Audited integrated run: strict eligibility, offline exports and baselines."""
from dataclasses import asdict
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path

import geopandas as gpd
import h3
import pandas as pd
from shapely.geometry import Polygon

from antenna_cell_placement.config import (
    MODULE_DIR, PLANNING_OUTPUT_DIR, CLEANED_RADIO_TOWERS_CSV,
    CLEANED_PHYSICAL_SITES_CSV, MS_BUILDING_FOOTPRINTS_TILES,
)
from antenna_cell_placement.gis_v2 import FEATURE_VERSION
from antenna_cell_placement.planning_score import SCORE_VERSION
from antenna_cell_placement.integrated_optimizer import CellSiteOptimizer, PlanningConstraints
from antenna_cell_placement.source_integrity import verify_sources, require_sources, group_ready, sha256


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False, default=str) + '\n', encoding='utf-8', newline='\n')


def export_frame(frame, directory, name):
    frame.to_csv(directory / (name + '.csv'), index=False)
    points = gpd.GeoDataFrame(frame, geometry=gpd.points_from_xy(frame.canonical_longitude, frame.canonical_latitude), crs=4326)
    (directory / (name + '.geojson')).write_text(points.to_json(), encoding='utf-8', newline='\n')


def run_planning(output_dir=None, scope='Tripoli', operator='all', resolution=8,
                 constraints=PlanningConstraints(), rooftops=True):
    verification = verify_sources()
    require_sources(verification)
    output = Path(output_dir or PLANNING_OUTPUT_DIR / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / 'source_verification.json', verification)
    print('Required sources verified. Extracting corrected features...', flush=True)
    optimizer = CellSiteOptimizer(operator=operator, verification=verification)
    pool = optimizer.build_candidate_pool(scope, resolution, constraints)
    shortlist = optimizer.find_priority_placements(pool, constraints)
    from antenna_cell_placement.planning_comparison import compare_rankings
    comparison_pool, comparison = compare_rankings(pool, constraints)
    export_frame(pool, output, 'candidates')
    export_frame(shortlist, output, 'shortlist')
    comparison_pool.to_parquet(output / 'comparison_candidates.parquet', index=False)
    write_json(output / 'comparison.json', comparison)

    from antenna_cell_placement.config import PLANNING_INVENTORY_DIR
    import shutil
    inventory = json.loads((PLANNING_INVENTORY_DIR / 'inventory_manifest.json').read_text(encoding='utf-8'))
    if inventory['owner_confirmed_almadar_records'] != 645 or not inventory['owner_attribution_correct']:
        raise ValueError('Historical owner attribution changed')
    for name in ('radio_references.csv', 'physical_sites.csv', 'source_crosswalk.csv', 'rejected_records.csv', 'reconciliation.json'):
        shutil.copy2(PLANNING_INVENTORY_DIR / name, output / name)
    write_json(output / 'inventory_audit.json', inventory)

    roof_report = {'status': 'not_requested'}
    if rooftops:
        if shortlist.empty or not group_ready(verification, 'footprints'):
            roofs = gpd.GeoDataFrame(columns=['building_id', 'geometry'], geometry='geometry', crs=4326)
            roof_report = {'status': 'no_eligible_areas' if shortlist.empty else 'source_unavailable'}
        else:
            from antenna_cell_placement.rooftop_candidates import shortlist_buildings
            # Explicit point-to-area adapter; point scores do not become roof scores.
            areas = shortlist.drop_duplicates('h3_index').copy()
            areas['expansion_rank'] = areas.recommendation_rank
            polygons = [Polygon([(lon, lat) for lat, lon in h3.cell_to_boundary(cell)]) for cell in areas.h3_index]
            areas = gpd.GeoDataFrame(areas, geometry=polygons, crs=4326)
            roofs, roof_report = shortlist_buildings(areas, tile_paths=MS_BUILDING_FOOTPRINTS_TILES)
            roof_report['status'] = 'preliminary_footprint_review'
        from antenna_cell_placement.rooftop_candidates import export_rooftops
        export_rooftops(roofs, output)
    from antenna_cell_placement.planning_map import generate_planning_map, write_overview, localize_maps
    from antenna_cell_placement.service_review import run_service_review
    from antenna_cell_placement.public_evidence import evaluate_public_evidence
    print('Building measured-service review and official-statistics audit...', flush=True)
    measurement_review = run_service_review(output / 'measurements', shortlist=shortlist)
    evaluate_public_evidence(output_path=output / 'public_evidence/public_evidence.json')
    summary = pd.read_csv(output / 'measurements/measured_service_summary.csv')
    generate_planning_map(shortlist, output, scope, summary)
    write_overview(output, comparison, inventory)
    localize_maps(output)
    after = verify_sources()
    if [(r['path'], r['actual_sha256']) for r in verification['sources']] != [(r['path'], r['actual_sha256']) for r in after['sources']]:
        raise ValueError('Source bytes changed during the run; outputs are incomplete')
    manifest = {
        'status': 'completed', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'base_commit': '2eca2dd45c1e8ac0dba496f5825d350dba088368',
        'ahmed_source_commit': '2c48a27494545988561acc4782e6b23530d33af0',
        'inventory_version': inventory['inventory_version'],
        'scope': scope, 'operator_scope': operator, 'h3_resolution': resolution,
        'feature_version': FEATURE_VERSION, 'score_version': SCORE_VERSION,
        'primary_uses_ml': False, 'constraints': asdict(constraints),
        'sources': verification, 'sources_unchanged_during_run': True,
        'candidate_count': len(pool), 'eligible_count': int(pool.eligible.sum()),
        'shortlist_count': len(shortlist), 'rooftop_review': roof_report,
        'measurement_review': {'eligible_measurements': measurement_review['eligible_measurements'],
                               'primary_ranking_modified': False,
                               'planning_support': measurement_review['planning_support']},
        'source_code_sha256': {p.name: sha256(p) for p in sorted(Path(__file__).parent.glob('*.py'))},
        'packages': {n: importlib.metadata.version(n) for n in ('numpy', 'pandas', 'geopandas', 'rasterio', 'shapely', 'pyproj', 'h3', 'folium')},
        'artifacts': {p.relative_to(output).as_posix(): sha256(p) for p in sorted(output.rglob('*')) if p.is_file()},
    }
    write_json(output / 'manifest.json', manifest)
    print(f'Completed: {len(pool)} candidates, {int(pool.eligible.sum())} eligible, {len(shortlist)} selected. {output}', flush=True)
    return manifest
