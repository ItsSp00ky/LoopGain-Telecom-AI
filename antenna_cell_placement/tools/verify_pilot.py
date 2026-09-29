"""Independent consistency checks for the real local measured-service outputs."""

import json
import hashlib

import h3
import numpy as np
import pandas as pd
from shapely.geometry import Point, shape

from antenna_cell_placement.collected_data import load_measurements
from antenna_cell_placement.config import MODULE_DIR, REPORTS_DIR, RECOMMENDATIONS_MAP_HTML


def main():
    report = json.loads((REPORTS_DIR / 'pilot_review.json').read_text())
    snapshot_path = MODULE_DIR / 'pilot_snapshot.json'
    snapshot = json.loads(snapshot_path.read_text())
    assert report['snapshot_version'] == snapshot['version']
    assert report['snapshot_sha256'] == hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
    assert report['training_days'] == snapshot['training_days']
    assert report['holdout_days'] == snapshot['holdout_days']
    assert report['pilot']['h3_r7'] == snapshot['pilot_h3_r7']
    for name, digest in snapshot['source_sha256'].items():
        assert hashlib.sha256((MODULE_DIR / name).read_bytes()).hexdigest() == digest
    summary = pd.read_csv(REPORTS_DIR / 'measured_service_summary.csv')
    measurements, _ = load_measurements()
    eligible = measurements.loc[measurements.review_eligible].copy()
    eligible['day'] = eligible.measured_at.dt.strftime('%Y-%m-%d')
    eligible['h3_r9'] = [h3.latlng_to_cell(y, x, 9) for y, x in zip(eligible.lat, eligible.lon)]
    eligible['h3_r8'] = eligible.h3_r9.map(lambda c: h3.cell_to_parent(c, 8))
    eligible['h3_r7'] = eligible.h3_r9.map(lambda c: h3.cell_to_parent(c, 7))
    assert len(eligible) == report['eligible_measurements'] == int(summary.sample_count.sum())
    assert not summary.duplicated(['mcc', 'mnc', 'net_type', 'h3_r8']).any()
    assert set(report['holdout_days']).isdisjoint(report['training_days'])
    assert max(report['training_days']) < min(report['holdout_days'])
    train = eligible.loc[eligible.day.isin(report['training_days'])]
    test = eligible.loc[eligible.day.isin(report['holdout_days'])]
    assert len(train) == report['training_samples']
    assert len(test) == report['holdout_samples']
    assert len(train) + len(test) == len(eligible)
    request = json.loads((REPORTS_DIR / 'pilot_data_request.json').read_text())
    assert request['pilot_h3_r7'] == snapshot['pilot_h3_r7']
    assert request['source_sha256'] == snapshot['source_sha256']
    pilot_identities = train.loc[train.h3_r7.eq(snapshot['pilot_h3_r7']),
                                 ['mcc', 'mnc', 'net_type', 'lac', 'cell_id']].drop_duplicates()
    assert len(request['measured_cell_identities']) == len(pilot_identities)
    for row in summary.itertuples():
        subset = eligible.loc[eligible.mcc.eq(row.mcc) & eligible.mnc.eq(row.mnc) & eligible.net_type.eq(row.net_type) & eligible.h3_r8.eq(row.h3_r8)]
        assert len(subset) == row.sample_count
        blocks = subset.groupby(['day', 'device', 'h3_r9'], dropna=False).dbm.median()
        assert np.isclose(blocks.median(), row.median_dbm)
    pilot = report['pilot']
    assert pilot['training_samples'] == int(train.h3_r7.eq(pilot['h3_r7']).sum())
    assert pilot['holdout_samples'] == int(test.h3_r7.eq(pilot['h3_r7']).sum())
    assert pilot['rf_validation_ready'] is False
    assert not report['rf_readiness']['simulation_enabled']
    geojson = json.loads((REPORTS_DIR / 'measured_service_areas.geojson').read_text())
    assert len(geojson['features']) == len(summary)
    for feature in geojson['features']:
        polygon = shape(feature['geometry'])
        cell = feature['properties']['h3_r8']
        lat, lon = h3.cell_to_latlng(cell)
        assert polygon.is_valid and polygon.covers(Point(lon, lat))
    # Independently recompute the reported later-day baseline on equal blocks.
    keys = ['mcc', 'mnc', 'net_type', 'h3_r8']
    train_blocks = train.groupby([*keys, 'day', 'device', 'h3_r9'], dropna=False).dbm.median()
    predictions = train_blocks.groupby(keys).median().rename('prediction')
    test_blocks = test.groupby([*keys, 'day', 'device', 'h3_r9'], dropna=False).dbm.median().reset_index()
    joined = test_blocks.merge(predictions.reset_index(), on=keys, how='left')
    scored = joined.dropna(subset=['prediction'])
    assert report['temporal_validation']['holdout_blocks'] == len(test_blocks)
    assert report['temporal_validation']['matched_blocks'] == len(scored)
    assert {row['day'] for row in report['temporal_validation']['by_holdout_day']} == set(report['holdout_days'])
    for day_result in report['temporal_validation']['by_holdout_day']:
        day_blocks = joined.loc[joined.day.eq(day_result['day'])]
        day_scored = day_blocks.dropna(subset=['prediction'])
        assert day_result['holdout_blocks'] == len(day_blocks)
        assert day_result['matched_blocks'] == len(day_scored)
        if len(day_scored):
            assert np.isclose((day_scored.prediction - day_scored.dbm).abs().mean(), day_result['mae_db'])
    if len(scored):
        assert np.isclose((scored.prediction - scored.dbm).abs().mean(), report['temporal_validation']['mae_db'])
    html = RECOMMENDATIONS_MAP_HTML.read_text()
    for layer in ['Measured service by operator and technology', 'Measured pilot area (review only)', 'Location conflicts requiring survey']:
        assert layer in html
    # Ensure reconciliation never drops a competing coordinate or claims survey truth.
    reconciliation = report['reconciliation']
    assert reconciliation['survey_resolved_identities'] == 0
    assert all(len(row['alternatives']) >= 2 for row in reconciliation['decisions'])
    checks = {'status': 'passed', 'eligible_measurements': len(eligible), 'service_groups': len(summary),
              'training_samples': len(train), 'holdout_samples': len(test),
              'pilot_area': pilot['h3_r7'], 'chronological_mae_db': report['temporal_validation']['mae_db'],
              'rf_validation_ready': False,
              'checks': ['frozen source hashes and evaluation split', 'pilot data-request identities',
                         'measurement conservation', 'operator/radio isolation', 'temporal separation',
                         'block-weighted statistics', 'pilot sample accounting', 'GeoJSON geometry validity',
                         'independent temporal-error recomputation', 'runtime map layers', 'conflict alternatives retained']}
    (REPORTS_DIR / 'pilot_integration_checks.json').write_text(json.dumps(checks, indent=2) + '\n')
    print(json.dumps(checks, indent=2))


if __name__ == '__main__':
    main()
