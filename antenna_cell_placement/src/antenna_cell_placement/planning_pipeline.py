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

    from antenna_cell_placement.data_cleaning import load_raw_records_from_sqlite
    from antenna_cell_placement.inventory_audit_v2 import audit_inventory
    raw = load_raw_records_from_sqlite()
    towers, sites = pd.read_csv(CLEANED_RADIO_TOWERS_CSV), pd.read_csv(CLEANED_PHYSICAL_SITES_CSV)
    scoped, clusters, inventory = audit_inventory(raw, towers, sites)
    owner = raw.owner_confirmed_almadar.fillna(False).astype(bool)
    inventory['owner_confirmed_almadar_records'] = int(owner.sum())
    # Raw operator text is intentionally preserved; attribution lives in the
    # cleaned inventory and source-scoped identity, not a rewritten raw field.
    owner_towers = towers.owner_confirmed_almadar.fillna(False).astype(bool)
    inventory['owner_confirmed_almadar_radio_groups'] = int(owner_towers.sum())
    inventory['owner_attribution_correct'] = bool(towers.loc[owner_towers, 'operator'].eq('Al-Madar').all())
    if inventory['owner_confirmed_almadar_records'] != 645 or inventory['owner_confirmed_almadar_radio_groups'] != 645 or not inventory['owner_attribution_correct']:
        raise ValueError('Owner-confirmed attribution differs from reviewed inventory')
    scoped.to_csv(output / 'radio_inventory_scoped.csv', index=False)
    clusters.to_csv(output / 'cluster_audit.csv', index=False)
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
    generate_planning_map(shortlist, output, scope)
    write_overview(output, comparison, inventory)
    localize_maps(output)
    after = verify_sources()
    if [(r['path'], r['actual_sha256']) for r in verification['sources']] != [(r['path'], r['actual_sha256']) for r in after['sources']]:
        raise ValueError('Source bytes changed during the run; outputs are incomplete')
    manifest = {
        'status': 'completed', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'base_commit': '8a2be6c928945ce8c52dba93e975e72aea0123d2',
        'ahmed_source_commit': '15dc13a021f12f259319d611dc291ab6de9e4bbe',
        'scope': scope, 'operator_scope': operator, 'h3_resolution': resolution,
        'feature_version': FEATURE_VERSION, 'score_version': SCORE_VERSION,
        'primary_uses_ml': False, 'constraints': asdict(constraints),
        'sources': verification, 'sources_unchanged_during_run': True,
        'candidate_count': len(pool), 'eligible_count': int(pool.eligible.sum()),
        'shortlist_count': len(shortlist), 'rooftop_review': roof_report,
        'source_code_sha256': {p.name: sha256(p) for p in sorted(Path(__file__).parent.glob('*.py'))},
        'packages': {n: importlib.metadata.version(n) for n in ('numpy', 'pandas', 'geopandas', 'rasterio', 'shapely', 'pyproj', 'h3', 'folium')},
        'artifacts': {p.relative_to(output).as_posix(): sha256(p) for p in sorted(output.rglob('*')) if p.is_file()},
    }
    write_json(output / 'manifest.json', manifest)
    print(f'Completed: {len(pool)} candidates, {int(pool.eligible.sum())} eligible, {len(shortlist)} selected. {output}', flush=True)
    return manifest
