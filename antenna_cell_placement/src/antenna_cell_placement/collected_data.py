"""Adapters for supplied collections; handset positions never become site positions."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from pyproj import Geod
import h3
from shapely.geometry import Point

from antenna_cell_placement.config import DATA_DIR, REPORTS_DIR
from antenna_cell_placement.collected_opencellid import _libya_boundary

NEW_DATA_DIR = DATA_DIR / 'new_data'
CELLMAPPER_RELATIVE = Path('libya_collected_antennas/cellmapper/cellmapper_libya_antennas.csv')
BEACON_RELATIVE = Path('libya_collected_antennas/beacondb/beacondb_libya_antennas.csv')


def _read(path):
    frame = pd.read_csv(path)
    frame['source_file'] = str(path)
    frame['source_row'] = np.arange(2, len(frame) + 2)
    return frame


def _validate(frame, lat, lon, identities, rat):
    """Return valid rows and a row-level rejection ledger; retain raw attributes."""
    frame = frame.copy()
    reasons = pd.Series('', index=frame.index)
    for name in [lat, lon, *identities]:
        frame[name] = pd.to_numeric(frame[name], errors='coerce')
    valid_id = pd.Series(True, index=frame.index)
    for name in identities:
        valid_id &= np.isfinite(frame[name]) & frame[name].ge(0) & frame[name].mod(1).eq(0)
    valid_id &= frame['mcc'].eq(606)
    reasons.loc[~valid_id] += 'invalid_identity;'
    frame[rat] = frame[rat].astype('string').str.strip().str.upper()
    reasons.loc[~frame[rat].isin(['GSM', 'UMTS', 'LTE', 'NR', 'CDMA'])] += 'invalid_radio;'
    coordinates = frame[lat].between(-90, 90) & frame[lon].between(-180, 180)
    inside = pd.Series(False, index=frame.index)
    boundary = _libya_boundary()
    inside.loc[coordinates] = [boundary.covers(Point(x, y)) for x, y in zip(frame.loc[coordinates, lon], frame.loc[coordinates, lat])]
    reasons.loc[~inside] += 'invalid_or_outside_libya_coordinate;'
    rejected = frame.loc[reasons.ne(''), ['source_file', 'source_row']].copy()
    rejected['rejection_reason'] = reasons.loc[reasons.ne('')]
    return frame.loc[reasons.eq('')].copy(), rejected


def load_cellmapper(directory=NEW_DATA_DIR):
    path = Path(directory) / CELLMAPPER_RELATIVE
    if not path.exists():
        return pd.DataFrame(), pd.DataFrame()
    identities = ['mcc', 'mnc', 'region_id', 'site_id', 'cell_id']
    valid, rejected = _validate(_read(path), 'latitude', 'longitude', identities, 'rat')
    # Only the canonical combined export is read; provider exports/JSON/master
    # are overlapping snapshots, not independent observations.
    key = ['mcc', 'mnc', 'rat', 'region_id', 'site_id', 'cell_id']
    valid['_seen'] = pd.to_datetime(valid['last_seen_iso'], errors='coerce', utc=True)
    valid = valid.sort_values('_seen', na_position='first', kind='stable').drop_duplicates(key, keep='last')
    return valid.drop(columns='_seen').reset_index(drop=True), rejected


def _numbers(value):
    if pd.isna(value):
        return []
    values = pd.to_numeric(pd.Series(str(value).split(',')), errors='coerce')
    return sorted(set(float(v) for v in values if pd.notna(v) and np.isfinite(v) and v > 0))


def cellmapper_raw_records(directory=NEW_DATA_DIR):
    """Adapt explicit tower IDs only, without deriving sites from cell IDs."""
    cells, _ = load_cellmapper(directory)
    rows = []
    for _, row in cells.iterrows():
        times = pd.to_datetime([row.first_seen_iso, row.last_seen_iso], errors='coerce', utc=True)
        rows.append({
            'record_id': f'collected:{row.source_row}',
            'mcc': str(int(row.mcc)), 'mnc': str(int(row.mnc)),
            'operator': None, 'rat': row.rat, 'rat_subtype': row.rat,
            'site_id': str(int(row.site_id)), 'region_id': str(int(row.region_id)),
            'latitude': row.latitude, 'longitude': row.longitude,
            'visible': pd.NA,  # Contributor verification is not visibility.
            'source_verified': str(row.verified).lower() == 'true',
            'first_seen_ms': int(times[0].value // 1_000_000) if pd.notna(times[0]) else pd.NA,
            'last_seen_ms': int(times[1].value // 1_000_000) if pd.notna(times[1]) else pd.NA,
            'channels': [int(v) for v in _numbers(row.earfcn_channels)],
            'bands': [int(v) for v in _numbers(row.bands)],
            # Sector bandwidth cannot be summed with overlapping tower snapshots.
            # Keep it in the source table, not in a fabricated tower total.
            'bandwidths': [], 'tower_type': row.tower_type,
            'has_timing_advance': int(pd.notna(row.loc_ta_method1) or pd.notna(row.loc_ta_method2)),
            'has_signal_strength': int(pd.notna(row.loc_ss_method1)),
            'source_file': row.source_file,
        })
    return pd.DataFrame(rows)


def load_measurements(directory=NEW_DATA_DIR, as_of='2026-09-29T19:00:00Z'):
    frames, rejected = [], []
    now = pd.Timestamp.now(tz='UTC') if as_of is None else pd.Timestamp(as_of)
    if now.tzinfo is None:
        now = now.tz_localize('UTC')
    for path in sorted(Path(directory).glob('*.csv')):
        frame = _read(path)
        if 'measured_at' not in frame or 'net_type' not in frame:
            raise ValueError(f'Unsupported root collection CSV: {path}')
        valid, bad = _validate(frame, 'lat', 'lon', ['mcc', 'mnc', 'lac', 'cell_id'], 'net_type')
        valid['measured_at'] = pd.to_datetime(valid.measured_at, format="mixed", errors='coerce', utc=True)
        timestamp_ok = valid.measured_at.notna() & valid.measured_at.le(now)
        bad_time = valid.loc[~timestamp_ok, ['source_file', 'source_row']].copy()
        bad_time['rejection_reason'] = 'invalid_or_future_measurement_timestamp;'
        rejected.extend([bad, bad_time])
        valid = valid.loc[timestamp_ok].copy()
        valid['dbm'] = pd.to_numeric(valid.dbm, errors='coerce')
        valid['accuracy'] = pd.to_numeric(valid.accuracy, errors='coerce')
        valid['signal_valid'] = valid.dbm.between(-150, -20)
        valid['neighboring'] = valid.neighboring.astype(str).str.lower().map({'true': True, 'false': False}).astype('boolean')
        valid['review_eligible'] = (valid.signal_valid & valid.accuracy.between(0, 100) & valid.neighboring.eq(False)).fillna(False)
        frames.append(valid)
    if not frames:
        return pd.DataFrame(), pd.DataFrame()
    frame = pd.concat(frames, ignore_index=True)
    key = ['mcc', 'mnc', 'net_type', 'lac', 'cell_id', 'measured_at', 'lat', 'lon', 'device', 'neighboring']
    return frame.drop_duplicates(key).reset_index(drop=True), pd.concat(rejected, ignore_index=True)


def load_beacon(directory=NEW_DATA_DIR):
    path = Path(directory) / BEACON_RELATIVE
    if not path.exists():
        return pd.DataFrame(), pd.DataFrame()
    frame, rejected = _validate(_read(path), 'beacondb_lat', 'beacondb_lon', ['mcc', 'mnc', 'area_code_lac_tac', 'cell_id'], 'radio_type')
    return frame.drop_duplicates(['mcc', 'mnc', 'radio_type', 'area_code_lac_tac', 'cell_id']), rejected


def annotate_measurements(candidates, measurements=None):
    result = candidates.copy()
    result['measurement_nearest_distance_m'] = np.nan
    result['measurement_count_1km'] = pd.NA
    result['measurement_context_available'] = False
    if measurements is None:
        measurements, _ = load_measurements()
    if result.empty or measurements.empty:
        return result
    valid = measurements.loc[measurements.review_eligible].reset_index(drop=True)
    if valid.empty:
        return result
    geod = Geod(ellps='WGS84')
    valid = valid.copy()
    valid['day'] = valid.measured_at.dt.strftime('%Y-%m-%d')
    valid['h3_r9'] = [h3.latlng_to_cell(lat, lon, 9) for lat, lon in zip(valid.lat, valid.lon)]
    neighbors = []
    nearest = []
    for row in result.itertuples():
        distance = geod.inv(np.full(len(valid), row.canonical_longitude),
                            np.full(len(valid), row.canonical_latitude), valid.lon.to_numpy(), valid.lat.to_numpy())[2]
        nearest.append(float(distance.min()))
        neighbors.append(np.flatnonzero(distance <= 1000))
    result['measurement_nearest_distance_m'] = np.round(nearest, 1)
    result['measurement_count_1km'] = [len(ids) for ids in neighbors]
    result['measurement_context_available'] = True
    for (mnc, rat), _ in valid.groupby(['mnc', 'net_type'], sort=True):
        column = f'measurement_mnc_{int(mnc)}_{rat.lower()}_median_dbm_1km'
        values = []
        for ids in neighbors:
            group = valid.iloc[ids].loc[lambda rows: rows.mnc.eq(mnc) & rows.net_type.eq(rat)]
            blocks = group.groupby(['day','device','h3_r9'], dropna=False).dbm.median()
            values.append(float(blocks.median()) if len(blocks) else np.nan)
        result[column] = values
    return result


def audit_collections(directory=NEW_DATA_DIR, output=REPORTS_DIR / 'collected_data_validation.json'):
    """Persist counts, source fingerprints, and rejected row references."""
    directory = Path(directory)
    report = {'policy': 'CellMapper explicit site IDs join site references. Phone measurements and BeaconDB are review context only. Duplicate derived exports are not additional evidence.', 'sources': {}}
    for name, loader in [('cellmapper', load_cellmapper), ('phone_measurements', load_measurements), ('beacondb', load_beacon)]:
        valid, rejected = loader(directory)
        files = ([directory / CELLMAPPER_RELATIVE] if name == 'cellmapper' else [directory / BEACON_RELATIVE] if name == 'beacondb' else sorted(directory.glob('*.csv')))
        existing = [p for p in files if p.exists()]
        input_rows = sum(len(pd.read_csv(p)) for p in existing)
        entry = {'input_rows': input_rows, 'retained_rows': len(valid), 'rejected_rows': len(rejected), 'duplicate_rows': input_rows - len(valid) - len(rejected), 'rejections': rejected.to_dict('records'), 'files': [{'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in existing]}
        if name == 'cellmapper' and len(valid):
            entry['explicit_site_identities'] = len(valid.drop_duplicates(['mcc', 'mnc', 'rat', 'region_id', 'site_id']))
            entry['source_verified_rows'] = int(valid.verified.astype(str).str.lower().eq('true').sum())
        if name == 'phone_measurements' and len(valid):
            entry['review_eligible_rows'] = int(valid.review_eligible.sum())
            entry['radio_counts'] = valid.net_type.value_counts().to_dict()
            entry['operator_counts'] = valid.mnc.value_counts().to_dict()
        report['sources'][name] = entry
    from antenna_cell_placement.collected_opencellid import import_pipeline
    _, ocid_report = import_pipeline()
    report['opencellid'] = ocid_report
    report['limitations'] = [
        'Boundary exclusions include coastal points outside the supplied polygon; they do not prove a false source record.',
        'CellMapper contributor verification is not an independent engineering survey.',
        'Phone dBm summaries are separated by RAT; generic dbm is not assumed to be RSRP.',
        'BeaconDB and OpenCellID may share upstream observations and are not independent confirmations.',
    ]
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    return report
