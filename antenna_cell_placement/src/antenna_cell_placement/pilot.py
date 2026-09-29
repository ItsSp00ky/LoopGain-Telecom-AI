"""Measured service review and a chronological pilot, without fabricated RF inputs."""

import hashlib
import json
from pathlib import Path

import h3
import numpy as np
import pandas as pd

from antenna_cell_placement.collected_data import NEW_DATA_DIR, load_measurements, load_cellmapper
from antenna_cell_placement.config import MODULE_DIR, REPORTS_DIR, RAW_SQLITE_PATH
from pyproj import Geod
GEOD = Geod(ellps="WGS84")
from antenna_cell_placement.reconciliation import reconcile_locations

SERVICE_KEYS = ['mcc', 'mnc', 'net_type', 'h3_r8']
SERVICE_COLUMNS = [*SERVICE_KEYS, 'sample_count', 'day_count', 'device_count', 'cell_count',
                   'spatial_bins_r9', 'median_dbm', 'p10_dbm', 'p90_dbm', 'median_lte_rsrp_dbm']
RF_REQUIRED = ['frequency_mhz', 'bandwidth_mhz', 'azimuth_bearing_deg', 'mechanical_tilt_deg',
               'electrical_tilt_deg', 'height_m', 'tx_power_dbm', 'feeder_loss_db',
               'gain_dbi', 'pattern_reference']
PILOT_SNAPSHOT = MODULE_DIR / 'pilot_snapshot.json'
IDENTITY = ['mcc', 'mnc', 'net_type', 'lac', 'cell_id']


def _pilot_split(frame, config_path, source_files):
    """Freeze cohort and time split; never promote a prior holdout into training."""
    if config_path is None:
        days = sorted(frame.day.unique())
        holdout_day = days[-1] if len(days) >= 2 else None
        return frame.loc[~frame.day.eq(holdout_day)].copy(), frame.loc[frame.day.eq(holdout_day)].copy() if holdout_day else frame.iloc[:0].copy(), None
    config_path = Path(config_path)
    config = json.loads(config_path.read_text())
    if config.get('version') not in (1, 2) or not config.get('training_days') or not config.get('holdout_days') or not config.get('pilot_h3_r7'):
        raise ValueError('Pilot snapshot needs version 1 or 2, training_days, holdout_days, and pilot_h3_r7')
    training_days, holdout_days = config['training_days'], config['holdout_days']
    if (len(set(training_days)) != len(training_days) or len(set(holdout_days)) != len(holdout_days)
            or set(training_days) & set(holdout_days) or max(training_days) >= min(holdout_days)):
        raise ValueError('Pilot training and holdout days must be distinct and chronological')
    expected = config.get('source_sha256')
    actual = {path.relative_to(MODULE_DIR).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in source_files if path.exists()}
    if expected is not None and actual != expected:
        raise ValueError('Pilot source snapshot changed; create a new versioned pilot config before rerunning')
    observed_days = set(frame.day.unique())
    if observed_days != set(training_days) | set(holdout_days):
        raise ValueError('Pilot observed days differ from the configured training and holdout days')
    train = frame.loc[frame.day.isin(training_days)].copy()
    holdout = frame.loc[frame.day.isin(holdout_days)].copy()
    return train, holdout, config


def _pilot_asset_review(train, pilot, directory):
    """Compare exact measured identities with validated private sector rows."""
    from antenna_cell_placement.operator_assets import evaluate_operator_assets

    audit, sectors = evaluate_operator_assets(directory, observed_path=None, return_validated=True)
    measured = train.loc[train.h3_r7.eq(pilot['h3_r7']), IDENTITY].drop_duplicates()
    identified = sectors.loc[sectors[['radio', 'mcc', 'mnc', 'area', 'cell']].ne('').all(axis=1)].copy()
    identified = identified.rename(columns={'radio': 'net_type', 'area': 'lac', 'cell': 'cell_id'})
    for name in ['mcc', 'mnc', 'lac', 'cell_id']:
        numeric = pd.to_numeric(identified[name], errors='coerce')
        identified = identified.loc[numeric.notna() & numeric.ge(0) & numeric.mod(1).eq(0)].copy()
        identified[name] = numeric.loc[identified.index].astype('int64')
    grouped = identified.groupby(IDENTITY, dropna=False).agg(
        sectors=('sector_id', 'size'), complete=('engineering_complete', 'sum')).reset_index()
    matched = measured.merge(grouped, on=IDENTITY, how='left', validate='one_to_one')
    counts = matched.sectors.fillna(0)
    result = {'status': 'review', 'measured_identities': len(measured),
              'matched_identities': int(counts.eq(1).sum()),
              'missing_identities': int(counts.eq(0).sum()),
              'ambiguous_identities': int(counts.gt(1).sum()),
              'complete_matched_identities': int((counts.eq(1) & matched.complete.eq(1)).sum()),
              'asset_file_sha256': {entry['file']: entry['sha256'] for entry in audit['source']['files']},
              'source_manifest_sha256': hashlib.sha256((Path(directory) / 'source_manifest.json').read_bytes()).hexdigest(),
              'quality_checks': audit['checks'], 'quality_thresholds_present': audit['thresholds'] is not None,
              'field_provenance_pct': audit['metrics']['field_provenance']['completeness_pct'],
              'survey_checkpoints': audit['metrics']['survey_checkpoints']['count'],
              'interpretation': 'Exact pilot cell identities in valid asset sectors; operator review and independent RF validation still required.'}
    return result


def _data_request(train, pilot, sources):
    group = train.loc[train.h3_r7.eq(pilot['h3_r7'])] if 'h3_r7' in pilot else train.iloc[:0]
    identities = group.groupby(IDENTITY, dropna=False).agg(
        training_samples=('dbm', 'size'), training_days=('day', 'nunique')).reset_index()
    return {'pilot_h3_r7': pilot.get('h3_r7'), 'selection_basis': 'training measurements only',
            'source_sha256': sources, 'measured_cell_identities': identities.to_dict('records'),
            'requested_asset_fields': ['sites.latitude', 'sites.longitude',
                                       'sites.coordinate_accuracy_m', 'sites.surveyed_at_utc',
                                       'survey_checkpoints.csv', 'sectors.radio', 'sectors.mcc',
                                       'sectors.mnc', 'sectors.area', 'sectors.cell',
                                       'sectors.frequency_mhz', 'sectors.bandwidth_mhz',
                                       'sectors.azimuth_deg', 'sectors.mechanical_tilt_deg',
                                       'sectors.electrical_tilt_deg', 'sectors.height_m',
                                       'sectors.tx_power_dbm', 'sectors.feeder_loss_db',
                                       'antenna_catalog.gain_dbi', 'antenna_catalog.pattern_reference'],
            'field_work': ['repeat pilot routes on additional days for both operators',
                           'record serving-cell identities and explicit signal metric types',
                           'independently survey conflicting site locations'],
            'limits': 'These identities are a collection target, not a complete network inventory.'}


def prepare_measurements(measurements):
    """Keep eligible observations and derive deterministic geographic/time blocks."""
    if measurements.empty:
        return pd.DataFrame(columns=[*SERVICE_COLUMNS, 'h3_r7', 'h3_r9', 'day', 'device', 'dbm', 'lat', 'lon', 'lac', 'cell_id'])
    frame = measurements.loc[measurements.review_eligible.fillna(False)].copy()
    frame['day'] = frame.measured_at.dt.strftime('%Y-%m-%d')
    frame['h3_r9'] = [h3.latlng_to_cell(lat, lon, 9) for lat, lon in zip(frame.lat, frame.lon)]
    # Use hierarchical parents so area assignment and map footprints agree.
    frame['h3_r8'] = frame.h3_r9.map(lambda cell: h3.cell_to_parent(cell, 8))
    frame['h3_r7'] = frame.h3_r9.map(lambda cell: h3.cell_to_parent(cell, 7))
    return frame


def service_summary(frame):
    """Summarize only measured areas, separating operator and radio technology.

    Quantiles weight each day/device/H3-9 block equally; hundreds of stationary
    samples do not masquerade as hundreds of independent spatial observations.
    """
    rows = []
    for identity, group in frame.groupby(SERVICE_KEYS, sort=True):
        blocks = group.groupby(['day', 'device', 'h3_r9'], dropna=False).dbm.median()
        rsrp = pd.to_numeric(group.get('rsrp', pd.Series(np.nan, index=group.index)), errors='coerce')
        rsrp_valid = rsrp.where(rsrp.between(-150, -20) & group.net_type.eq('LTE'))
        rsrp_blocks = group.assign(_rsrp=rsrp_valid).groupby(['day', 'device', 'h3_r9'], dropna=False)._rsrp.median().dropna()
        rows.append({
            **dict(zip(SERVICE_KEYS, identity)), 'sample_count': len(group),
            'day_count': group.day.nunique(), 'device_count': group.device.nunique(),
            'cell_count': len(group[['lac', 'cell_id']].drop_duplicates()),
            'spatial_bins_r9': group.h3_r9.nunique(), 'median_dbm': float(blocks.median()),
            'p10_dbm': float(blocks.quantile(.1)), 'p90_dbm': float(blocks.quantile(.9)),
            'median_lte_rsrp_dbm': float(rsrp_blocks.median()) if len(rsrp_blocks) else np.nan,
        })
    return pd.DataFrame(rows, columns=SERVICE_COLUMNS)


def chronological_baseline(train, holdout):
    """Evaluate a measured-area median baseline on a later day, never RF coverage."""
    result = {'status': 'unavailable', 'method': 'Training day/device/H3-9 block medians, aggregated by operator/RAT/H3-8; equal holdout block weighting.',
              'holdout_blocks': 0, 'matched_blocks': 0, 'coverage_pct': 0.0, 'mae_db': None,
              'bias_db': None, 'by_operator_radio': [], 'by_holdout_day': []}
    if train.empty or holdout.empty:
        return result
    assert set(train.day).isdisjoint(set(holdout.day)), 'Training and holdout days must be disjoint'
    prediction = service_summary(train)[[*SERVICE_KEYS, 'median_dbm']].rename(columns={'median_dbm': 'prediction_dbm'})
    blocks = holdout.groupby([*SERVICE_KEYS, 'day', 'device', 'h3_r9'], dropna=False).dbm.median().reset_index()
    scored = blocks.merge(prediction, on=SERVICE_KEYS, how='left', validate='many_to_one')
    known = scored.dropna(subset=['prediction_dbm']).copy()
    result.update(holdout_blocks=len(blocks), matched_blocks=len(known), coverage_pct=round(100 * len(known) / len(blocks), 2))
    for day, day_blocks in scored.groupby('day', sort=True):
        matched = day_blocks.dropna(subset=['prediction_dbm'])
        errors = matched.prediction_dbm - matched.dbm
        result['by_holdout_day'].append({
            'day': day, 'holdout_blocks': len(day_blocks), 'matched_blocks': len(matched),
            'coverage_pct': round(100 * len(matched) / len(day_blocks), 2),
            'mae_db': float(errors.abs().mean()) if len(errors) else None,
            'bias_db': float(errors.mean()) if len(errors) else None,
        })
    if known.empty:
        return result
    known['error'] = known.prediction_dbm - known.dbm
    result.update(status='evaluated', mae_db=float(known.error.abs().mean()), bias_db=float(known.error.mean()))
    for (mcc, mnc, radio), group in known.groupby(['mcc', 'mnc', 'net_type']):
        result['by_operator_radio'].append({'mcc': int(mcc), 'mnc': int(mnc), 'radio': radio,
                                          'blocks': len(group), 'mae_db': float(group.error.abs().mean()),
                                          'bias_db': float(group.error.mean())})
    return result


def select_pilot(train, towers):
    """Choose a bounded H3-7 area using training support alone, with a review gate."""
    if train.empty:
        return {'status': 'unavailable', 'reason': 'No eligible training measurements'}
    reliable = towers.loc[~towers.location_conflict & towers.source_verified.fillna(False)].copy()
    candidates = []
    for area, group in train.groupby('h3_r7', sort=True):
        spatial_bins = group.h3_r9.nunique()
        cells = len(group[['mcc', 'mnc', 'net_type', 'lac', 'cell_id']].drop_duplicates())
        if len(group) < 20 or spatial_bins < 3 or cells < 2:
            continue
        lat, lon = h3.cell_to_latlng(area)
        pairs = set(zip(group.mnc.astype(int).astype(str), group.net_type))
        matching = reliable.loc[[ (str(row.mnc), row.rat) in pairs for row in reliable.itertuples() ]]
        nearby = 0
        if len(matching):
            distances = GEOD.inv(np.full(len(matching), lon), np.full(len(matching), lat), matching.longitude.to_numpy(), matching.latitude.to_numpy())[2]
            nearby = int((distances <= 5000).sum())
        candidates.append({'h3_r7': area, 'latitude': lat, 'longitude': lon,
                           'training_samples': len(group), 'training_spatial_bins_r9': spatial_bins,
                           'training_days': group.day.nunique(), 'training_cells': cells,
                           'nearby_source_verified_nonconflicting_references': nearby})
    if not candidates:
        return {'status': 'unavailable', 'reason': 'No training area meets 20 samples, 3 spatial bins, and 2 cell identities'}
    candidates.sort(key=lambda row: (-int(row['nearby_source_verified_nonconflicting_references'] > 0),
                                    -row['training_days'], -row['training_spatial_bins_r9'], -row['training_cells'], row['h3_r7']))
    return {'status': 'measured_review_only', **candidates[0], 'qualifying_training_areas': len(candidates),
            'selection_policy': 'Training data only; prefer nearby nonconflicting source-verified references, then days, spatial bins, and cell identities. Counts do not establish survey accuracy.',
            'rf_validation_ready': False}


def match_sector_identities(frame, cells):
    """Exact full identity only; never derive a mast location from a phone fix."""
    key = ['mcc', 'mnc', 'net_type', 'lac', 'cell_id']
    identities = frame[key].drop_duplicates()
    if cells.empty:
        return {'measurement_identities': len(identities), 'matched_identities': 0}
    known = cells.rename(columns={'rat': 'net_type', 'region_id': 'lac'})[key].drop_duplicates()
    paired = identities.merge(known, on=key, how='inner', validate='one_to_one')
    return {'measurement_identities': len(identities), 'matched_identities': len(paired),
            'interpretation': 'Exact MCC/MNC/RAT/area/cell matching; unmatched observations remain useful measured service evidence.'}


def rf_readiness(cells, matches):
    """Report missing engineering inputs; received signal is never transmit power."""
    counts = {}
    complete = pd.Series(True, index=cells.index)
    ranges = {'frequency_mhz': (1, 100000), 'bandwidth_mhz': (.01, 10000),
              'azimuth_bearing_deg': (0, 359.999999), 'mechanical_tilt_deg': (-90, 90),
              'electrical_tilt_deg': (-90, 90), 'height_m': (.1, 1000),
              'tx_power_dbm': (-100, 100), 'feeder_loss_db': (0, 100), 'gain_dbi': (-20, 60)}
    for column in RF_REQUIRED:
        values = cells.get(column, pd.Series(index=cells.index, dtype=object))
        valid = values.notna() & values.astype(str).str.strip().ne('')
        if column in ranges:
            valid &= pd.to_numeric(values, errors='coerce').between(*ranges[column])
        counts[column] = int(valid.sum())
        complete &= valid
    return {'status': 'not_ready', 'simulation_enabled': False,
            'sector_rows': len(cells), 'engineering_complete_sectors': int(complete.sum()),
            'valid_field_counts': counts, 'missing_everywhere': [name for name, count in counts.items() if not count],
            'exact_measurement_sector_matches': matches['matched_identities'],
            'requirements': ['Surveyed site coordinates with provenance', 'Complete per-sector engineering parameters and antenna pattern',
                             'Exact measurement/sector associations', 'Independent RF validation and approved error thresholds'],
            'interpretation': 'Input-readiness audit only. No antenna height, frequency, transmit power, tilt, or propagation predictions are invented.'}


def _json_safe(value):
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def _cell_geometry(cell):
    ring = [[lon, lat] for lat, lon in h3.cell_to_boundary(cell)]
    return {'type': 'Polygon', 'coordinates': [ring + [ring[0]]]}


def build_pilot_review(directory=NEW_DATA_DIR, output_dir=REPORTS_DIR, towers=None,
                       config_path=None, asset_directory=None):
    from antenna_cell_placement.data_cleaning import (load_raw_records_from_sqlite, deduplicate_radio_towers)
    from antenna_cell_placement.collected_data import cellmapper_raw_records, CELLMAPPER_RELATIVE

    directory, output_dir = Path(directory), Path(output_dir)
    if towers is None:
        raw = load_raw_records_from_sqlite()
        raw['source_file'] = str(RAW_SQLITE_PATH)
        from antenna_cell_placement.collected_inventory import group_radio_records
        raw['record_id'] = 'sqlite:' + raw.record_id.astype(str)
        towers, _ = group_radio_records(pd.concat([raw, cellmapper_raw_records(directory)], ignore_index=True))
    measurements, _ = load_measurements(directory)
    cells, _ = load_cellmapper(directory)
    frame = prepare_measurements(measurements)
    source_files = [RAW_SQLITE_PATH, directory / CELLMAPPER_RELATIVE, *sorted(directory.glob('*.csv'))]
    if config_path is None and directory.resolve() == NEW_DATA_DIR.resolve():
        config_path = PILOT_SNAPSHOT
    train, holdout, config = _pilot_split(frame, config_path, source_files)
    holdout_days = sorted(holdout.day.unique())
    holdout_day = holdout_days[0] if len(holdout_days) == 1 else None
    pilot = select_pilot(train, towers)
    if config is not None and pilot.get('h3_r7') != config['pilot_h3_r7']:
        raise ValueError('Selected pilot area differs from the frozen snapshot')
    if 'h3_r7' in pilot:
        pilot_train = train.loc[train.h3_r7.eq(pilot['h3_r7'])]
        pilot_holdout = holdout.loc[holdout.h3_r7.eq(pilot['h3_r7'])]
        pilot['holdout_samples'] = len(pilot_holdout)
        pilot['temporal_validation'] = chronological_baseline(pilot_train, pilot_holdout)
    matches = match_sector_identities(frame, cells)
    summary = service_summary(frame)
    from antenna_cell_placement.collected_inventory import AS_OF
    reconciliation = reconcile_locations(towers, as_of=AS_OF)
    sources = [{'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
               for path in source_files if path.exists()]
    asset_review = _pilot_asset_review(train, pilot, asset_directory) if asset_directory is not None and 'h3_r7' in pilot else None
    report = {
        'status': 'review_ready' if len(frame) else 'no_eligible_measurements',
        'eligible_measurements': len(frame), 'service_area_operator_radio_groups': len(summary),
        'training_days': sorted(train.day.unique()), 'holdout_day': holdout_day,
        'holdout_days': holdout_days, 'snapshot_version': config['version'] if config else None,
        'snapshot_sha256': hashlib.sha256(Path(config_path).read_bytes()).hexdigest() if config else None,
        'training_samples': len(train), 'holdout_samples': len(holdout),
        'reconciliation': reconciliation, 'pilot': pilot, 'sector_identity_matching': matches,
        'temporal_validation': chronological_baseline(train, holdout), 'rf_readiness': rf_readiness(cells, matches),
        'operator_asset_review': asset_review, 'sources': sources,
        'limitations': ['Measurements describe the collected routes, days, devices, and networks only.',
                       'Service summaries separate operators and technologies; generic dBm is not RSRP.',
                       'The held-out-day median baseline measures temporal repeatability, not RF prediction accuracy.',
                       'Pilot selection never uses held-out signal values or held-out sample support.',
                       'Conflicted locations remain conservative screening references, not reliable pilot anchors.',
                       'No measured-area summary changes national placement scores.'],
    }
    report = _json_safe(report)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / 'pilot_review.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    summary.to_csv(output_dir / 'measured_service_summary.csv', index=False)
    features = [{'type': 'Feature', 'geometry': _cell_geometry(row['h3_r8']), 'properties': _json_safe(row)} for row in summary.to_dict('records')]
    (output_dir / 'measured_service_areas.geojson').write_text(json.dumps({'type': 'FeatureCollection', 'features': features}, allow_nan=False) + '\n')
    (output_dir / 'pilot_review.md').write_text(_review_markdown(report))
    request = _json_safe(_data_request(train, pilot, {path.relative_to(MODULE_DIR).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                                                for path in source_files if path.exists() and path.is_relative_to(MODULE_DIR)}))
    (output_dir / 'pilot_data_request.json').write_text(json.dumps(request, indent=2, allow_nan=False) + '\n')
    return report


def _review_markdown(report):
    pilot, validation, readiness = report['pilot'], report['temporal_validation'], report['rf_readiness']
    lines = ['# Measured service and pilot review', '',
             f"Eligible phone measurements: **{report['eligible_measurements']:,}**. Operator/technology/area groups: **{report['service_area_operator_radio_groups']}**.", '',
             f"Training days: {', '.join(report['training_days']) or 'none'}. Held-out days: {', '.join(report['holdout_days']) or 'unavailable'}. Snapshot version: {report['snapshot_version'] or 'unfrozen fixture'}.", '',
             '## Location reconciliation', '',
             f"{report['reconciliation']['conflicted_identities']} conflicting identities; {report['reconciliation']['preferred_for_review']} provisional preferences; 0 resolved by independent survey.", '',
             '| Network / radio / area / site | Separation | Decision |', '| --- | ---: | --- |']
    for row in report['reconciliation']['decisions']:
        lines.append(f"| {row['mcc']}/{row['mnc']} / {row['rat']} / {row['region_id']} / {row['site_id']} | {row['maximum_separation_m']/1000:.2f} km | {row['status']} |")
    lines += ['', 'All alternatives and their timestamps, verification flags, and source paths are in `pilot_review.json`. Obtain surveyed or operator-provided coordinates to resolve these conflicts.', '',
              '## Pilot area', '', f"Status: **{pilot['status']}**."]
    if 'h3_r7' in pilot:
        lines += [f"H3 area: `{pilot['h3_r7']}`; center: {pilot['latitude']:.6f}, {pilot['longitude']:.6f}.",
                  f"Training: {pilot['training_samples']} samples across {pilot['training_spatial_bins_r9']} spatial bins and {pilot['training_days']} days. Held-out samples: {pilot['holdout_samples']}.",
                  f"Nearby matching-network/technology source-verified, nonconflicting references: {pilot['nearby_source_verified_nonconflicting_references']} (within 5 km of area center).",
                  f"Pilot-only temporal validation: {pilot['temporal_validation']['status']}; matched blocks: {pilot['temporal_validation']['matched_blocks']}."]
    else:
        lines.append(pilot['reason'])
    lines += ['', '## Held-out measurement baseline', '',
              f"Status: {validation['status']}. Matched {validation['matched_blocks']} of {validation['holdout_blocks']} blocks ({validation['coverage_pct']}%).",
              f"Mean absolute error: {validation['mae_db']} dB; bias: {validation['bias_db']} dB. These describe a historical measured-area median baseline, not an RF simulation or a pass against an engineering acceptance threshold.", '',
              '| Held-out day | Matched blocks | Coverage | MAE (dB) |', '| --- | ---: | ---: | ---: |',
              *[f"| {row['day']} | {row['matched_blocks']}/{row['holdout_blocks']} | {row['coverage_pct']}% | {row['mae_db'] if row['mae_db'] is not None else 'Unavailable'} |" for row in validation['by_holdout_day']], '',
              '## RF input readiness', '', f"Status: **{readiness['status']}**. Complete engineering sectors: {readiness['engineering_complete_sectors']}. Exact measured cell/sector identity matches: {readiness['exact_measurement_sector_matches']}.",
              f"Fields absent from all supplied sectors: {', '.join(readiness['missing_everywhere'])}.", '',
              '## Operator asset comparison', '',
              ('No authorized operator export selected.' if report['operator_asset_review'] is None else
               f"Valid export matches: {report['operator_asset_review']['matched_identities']}/{report['operator_asset_review']['measured_identities']} pilot identities; {report['operator_asset_review']['missing_identities']} missing, {report['operator_asset_review']['ambiguous_identities']} ambiguous, {report['operator_asset_review']['complete_matched_identities']} with complete engineering fields. Status: review."), '',
              'The pilot-specific identity and field request is in `pilot_data_request.json`.', '',
              'Next field work: revisit the pilot on additional days; collect comparable observations for both operators; export sector identities and engineering parameters; independently survey the conflicting locations. Keep the held-out day separate from any calibration.', '',
              '## Limitations', '', *[f'- {item}' for item in report['limitations']], '']
    return '\n'.join(lines)
