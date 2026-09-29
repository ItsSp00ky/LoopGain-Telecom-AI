"""Isolated empirical RF method benchmark on real, non-Libyan measurements."""

import hashlib
import json
from pathlib import Path

import h3
import numpy as np
import pandas as pd
from pyproj import Geod

from antenna_cell_placement.config import EXTERNAL_DATA_DIR, REPORTS_DIR


SOURCE_DIR = EXTERNAL_DATA_DIR / 'chongqing_5g_2026'
GEOD = Geod(ellps='WGS84')
RAW_COLUMNS = {'TIME(BeiJing)', 'LATITUDE', 'LONGITUDE', 'ACCURACY(M)',
               'IS_OUTDOOR', 'NETWORK_TYPE', 'NCI', 'SS_RSRP'}
BASE_COLUMNS = {'ECI', 'LONGITUDE (processed)', 'LATITUDE (processed)'}


def _verify(directory):
    manifest = json.loads((directory / 'manifest.json').read_text())
    for name, metadata in manifest['files'].items():
        data = (directory / name).read_bytes()
        if (len(data) != metadata['bytes'] or hashlib.sha256(data).hexdigest() != metadata['sha256']
                or hashlib.md5(data).hexdigest() != metadata['zenodo_md5']):
            raise ValueError(f'Foreign RF source hash or size mismatch: {name}')
    return manifest


def _holdout(cell):
    """Predeclared, deterministic 20% assignment of H3-8 areas."""
    return hashlib.sha256(cell.encode()).digest()[0] % 5 == 0


def _score(y, estimate):
    error = np.asarray(estimate, dtype=float) - np.asarray(y, dtype=float)
    return {'mae_db': round(float(np.mean(np.abs(error))), 3),
            'p90_absolute_error_db': round(float(np.quantile(np.abs(error), .9)), 3),
            'bias_db': round(float(np.mean(error)), 3)}


def evaluate_foreign_rf_benchmark(directory=SOURCE_DIR,
                                  output_path=REPORTS_DIR / 'foreign_rf_benchmark.json'):
    """Compare a measured-cell median with a fitted distance curve on unseen areas.

    No source measurements or site parameters are copied into Libya outputs.
    """
    directory = Path(directory)
    manifest = _verify(directory)
    raw = pd.read_csv(directory / 'raw_datas.csv')
    base = pd.read_csv(directory / 'base_station_data.csv')
    if not RAW_COLUMNS.issubset(raw) or not BASE_COLUMNS.issubset(base):
        raise ValueError('Foreign RF source schema changed')
    if base.ECI.duplicated().any():
        raise ValueError('Foreign base-station ECI is not unique')
    total_rows = len(raw)
    raw['day'] = pd.to_datetime(raw['TIME(BeiJing)'], format='%Y%m%d %H:%M:%S.%f',
                                errors='coerce').dt.strftime('%Y-%m-%d')
    eligible = raw.loc[
        raw.NETWORK_TYPE.eq('SA') & raw.IS_OUTDOOR.eq(1)
        & raw['ACCURACY(M)'].between(0, 50)
        & raw.SS_RSRP.between(-140, -40)
        & raw.LATITUDE.between(-90, 90) & raw.LONGITUDE.between(-180, 180)
        & raw.day.notna()
    ].copy()
    joined = eligible.merge(base[['ECI', 'LONGITUDE (processed)', 'LATITUDE (processed)']],
                            left_on='NCI', right_on='ECI', how='inner', validate='many_to_one')
    _, _, distance = GEOD.inv(joined.LONGITUDE.to_numpy(), joined.LATITUDE.to_numpy(),
                              joined['LONGITUDE (processed)'].to_numpy(),
                              joined['LATITUDE (processed)'].to_numpy())
    joined['distance_m'] = distance
    joined = joined.loc[joined.distance_m.between(50, 30000)].copy()
    joined['h3_r10'] = [h3.latlng_to_cell(lat, lon, 10) for lat, lon in zip(joined.LATITUDE, joined.LONGITUDE)]
    joined['h3_r8'] = joined.h3_r10.map(lambda cell: h3.cell_to_parent(cell, 8))
    # One observation per cell/day/small spatial block curbs repeated stationary logs.
    blocks = joined.groupby(['NCI', 'day', 'h3_r8', 'h3_r10'], as_index=False).agg(
        rsrp_dbm=('SS_RSRP', 'median'), distance_m=('distance_m', 'median'),
        raw_samples=('SS_RSRP', 'size'))
    areas = sorted(blocks.h3_r8.unique())
    holdout_areas = {area for area in areas if _holdout(area)}
    train = blocks.loc[~blocks.h3_r8.isin(holdout_areas)].copy()
    test = blocks.loc[blocks.h3_r8.isin(holdout_areas)].copy()
    models = []
    for nci, group in train.groupby('NCI', sort=True):
        if len(group) < 20 or group.h3_r8.nunique() < 2 or group.distance_m.max() - group.distance_m.min() < 100:
            continue
        x = np.log10(group.distance_m.to_numpy())
        y = group.rsrp_dbm.to_numpy()
        slope, intercept = np.polyfit(x, y, 1)
        models.append({'NCI': nci, 'baseline_dbm': float(np.median(y)),
                       'slope': float(slope), 'intercept': float(intercept)})
    scored = test.merge(pd.DataFrame(models, columns=['NCI', 'baseline_dbm', 'slope', 'intercept']),
                        on='NCI', how='inner', validate='many_to_one')
    status = 'unavailable'
    baseline = model = None
    improvement = None
    if len(scored):
        baseline = _score(scored.rsrp_dbm, scored.baseline_dbm)
        prediction = scored.intercept + scored.slope * np.log10(scored.distance_m)
        model = _score(scored.rsrp_dbm, prediction)
        improvement = round(100 * (baseline['mae_db'] - model['mae_db']) / baseline['mae_db'], 2)
        status = 'evaluated'
    distance_decision = ('do_not_use' if improvement is not None and improvement <= 0
                         else 'exploratory_only' if improvement is not None else 'unavailable')
    report = {
        'status': status, 'decision': 'method_review_only',
        'distance_model_decision': distance_decision, 'dataset_country': manifest['country'],
        'dataset_city': manifest['city'], 'source_doi': manifest['doi'],
        'source_sha256': {name: metadata['sha256'] for name, metadata in manifest['files'].items()},
        'source_quality': {'raw_rows': total_rows, 'eligible_sa_outdoor_rows': len(eligible),
                           'rows_with_exact_nci_eci_match_and_valid_distance': len(joined),
                           'raw_cells': int(raw.NCI.nunique()), 'matched_cells': int(joined.NCI.nunique()),
                           'base_station_rows': len(base), 'measured_blocks': len(blocks)},
        'evaluation': {'holdout_policy': 'SHA-256(H3-8 ID) first byte modulo 5 equals zero; complete H3-8 areas held out',
                       'training_areas': len(areas) - len(holdout_areas), 'holdout_areas': len(holdout_areas),
                       'training_blocks': len(train), 'holdout_blocks': len(test),
                       'eligible_fitted_cells': len(models), 'scored_holdout_blocks': len(scored),
                       'scored_holdout_support_pct': round(100 * len(scored) / len(test), 2) if len(test) else 0.0,
                       'scored_holdout_cells': int(scored.NCI.nunique()),
                       'baseline': baseline, 'distance_model': model,
                       'distance_model_mae_improvement_pct': improvement,
                       'baseline_method': 'Per-cell median SS-RSRP from training blocks',
                       'treatment_method': 'Per-cell least-squares SS-RSRP versus log10(measured distance to source base coordinate)',
                       'sample_weight': 'One median per cell/day/H3-10 block; equal block weight'},
        'limitations': ['Foreign 5G NR data evaluates only the measurement and geographic holdout method.',
                        'Operator base-station coordinates are anonymized/processed, not independently surveyed.',
                        'No antenna pattern, receiver height, or full calibrated RF simulator is used.',
                        'This result cannot validate Libya coverage, RF errors, frequency bands, or site placement.',
                        'The source grid includes interpolated values; this audit uses raw_datas.csv only.'],
    }
    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    return report
