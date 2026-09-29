"""Check the actual local collection integration and rebuilt recommendation artifacts."""
import json

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from antenna_cell_placement.collected_data import load_cellmapper, load_measurements
from antenna_cell_placement.config import RECOMMENDATIONS_CSV, RECOMMENDATIONS_GEOJSON, RECOMMENDATIONS_MAP_HTML, REPORTS_DIR
from antenna_cell_placement.data_cleaning import clean_pipeline, load_raw_records_from_sqlite, deduplicate_radio_towers
from antenna_cell_placement.opencellid import projected


def main():
    cells, _ = load_cellmapper()
    measurements, _ = load_measurements()
    towers, sites = clean_pipeline()
    baseline = deduplicate_radio_towers(load_raw_records_from_sqlite())
    key = ['mcc', 'mnc', 'rat', 'region_id', 'site_id']
    def identities(frame):
        return set(map(tuple, frame[key].astype(str).to_numpy()))
    collected = cells.copy()
    for name in ['mcc', 'mnc', 'region_id', 'site_id']:
        collected[name] = collected[name].astype(int).astype(str)
    assert identities(collected).issubset(identities(towers)), 'Collected site identities missing from runtime'
    assert not towers.duplicated([*key, 'location_group']).any(), 'Duplicate runtime tower identities'
    recommendations = pd.read_csv(RECOMMENDATIONS_CSV)
    assert len(recommendations) > 0
    assert recommendations.candidate_id.is_unique
    assert recommendations.planning_priority_score.is_monotonic_decreasing
    assert recommendations.planning_priority_score.between(0, 100).all()
    assert recommendations.population_sum_5km.ge(300).all()
    assert recommendations.dist_to_nearest_road_m.le(4000).all()
    assert not recommendations.worldcover_is_water.any()
    assert recommendations.worldcover_data_available.all()
    coordinates = projected(recommendations.canonical_longitude, recommendations.canonical_latitude)
    tree = cKDTree(projected(sites.canonical_longitude, sites.canonical_latitude))
    gaps = tree.query(coordinates)[0]
    assert (gaps >= 3000).all(), 'Proposal within exclusion distance of expanded inventory'
    assert np.allclose(gaps, recommendations.dist_to_nearest_site_m, atol=0.2)
    separation = cKDTree(coordinates).query(coordinates, k=2)[0][:, 1]
    assert (separation >= 2500).all()
    geojson = json.loads(RECOMMENDATIONS_GEOJSON.read_text())
    assert len(geojson['features']) == len(recommendations)
    assert {f['properties']['candidate_id'] for f in geojson['features']} == set(recommendations.candidate_id)
    for feature, (_, row) in zip(geojson['features'], recommendations.iterrows()):
        assert np.allclose(feature['geometry']['coordinates'], [row.canonical_longitude, row.canonical_latitude])
    html = RECOMMENDATIONS_MAP_HTML.read_text()
    assert 'Phone signal measurements (receiver locations)' in html
    assert 'BeaconDB geolocation estimates' in html
    assert 'nan,' not in html.lower(), 'Nonfinite map coordinate'
    report = {
        'status': 'passed', 'baseline_network_scoped_towers': len(baseline),
        'runtime_towers': len(towers), 'runtime_site_references': len(sites),
        'location_conflict_references': int(towers.location_conflict.sum()),
        'location_conflicts': towers.loc[towers.location_conflict, [*key, 'location_group', 'latitude', 'longitude', 'source_files']].to_dict('records'),
        'new_radio_site_identities': len(identities(towers) - identities(baseline)),
        'retained_cellmapper_sectors': len(cells), 'retained_phone_measurements': len(measurements),
        'recommendations': len(recommendations), 'minimum_known_site_gap_m': float(gaps.min()),
        'minimum_candidate_separation_m': float(separation.min()),
        'recommendations_with_phone_measurements_within_1km': int(recommendations.measurement_count_1km.gt(0).sum()),
        'checks': ['collected identities present', 'network-scoped identity uniqueness', 'priority ordering and range',
                   'population, road and land-cover constraints', 'independently recomputed site gaps',
                   'candidate separation', 'CSV/GeoJSON identity and coordinate agreement', 'new map layers present'],
        'limitations': 'Checks validate software and supplied-data consistency, not RF performance or surveyed tower accuracy.',
    }
    path = REPORTS_DIR / 'collected_data_integration_checks.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
