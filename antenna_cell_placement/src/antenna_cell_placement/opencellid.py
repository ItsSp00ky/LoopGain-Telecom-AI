"""Validate OpenCellID observations without treating them as mast or coverage truth."""

from pathlib import Path
from functools import lru_cache

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree
from shapely.geometry import Point

from antenna_cell_placement.config import (
    OPENCELLID_RAW_PATH,
    ADMIN0_GEOJSON_PATH,
    CRS_PROJECTED_LIBYA,
    CRS_WGS84,
)

COLUMNS = 'radio mcc net area cell unit lon lat range samples changeable created updated averageSignal'.split()
IDENTITY = ['radio', 'mcc', 'net', 'area', 'cell']


def load_cells(path: Path, as_of=None):
    """Read headerless or named exports; quarantine invalid identity/location rows.

    ``unit`` is PSC for UMTS and PCI for LTE. ``range`` is an estimated source
    value, not a coverage radius or accuracy. Deprecated ``changeable`` and
    ``averageSignal`` are retained for provenance and excluded from decisions.
    """
    raw = pd.read_csv(path, header=None, dtype=str)
    if raw.empty:
        raise ValueError("OpenCellID input is empty")
    # Named collected exports may append provider/country provenance columns.
    if set(COLUMNS).issubset(raw.iloc[0].str.strip().tolist()):
        raw.columns = raw.iloc[0].str.strip().tolist()
        raw = raw.iloc[1:][COLUMNS].copy()
    if raw.shape[1] != len(COLUMNS):
        raise ValueError(f'Expected 14 OpenCellID columns, found {raw.shape[1]}')
    if not raw.empty and raw.iloc[0].str.strip().tolist() == COLUMNS:
        raw = raw.iloc[1:].copy()
    raw.columns = COLUMNS
    return _validate_cells(raw, str(path), as_of)


def _validate_cells(raw, source, as_of=None):
    df = raw.copy()
    df['radio'] = df['radio'].str.strip().str.upper()
    for col in COLUMNS[1:]:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    valid = df['radio'].isin(['GSM', 'UMTS', 'LTE', 'CDMA', 'NR'])
    for col in ['mcc', 'net', 'area', 'cell']:
        valid &= df[col].notna() & np.isfinite(df[col]) & (df[col] >= 0) & (df[col] % 1 == 0)
    valid &= df['mcc'].eq(606)
    valid &= df['lat'].between(-90, 90) & df['lon'].between(-180, 180)
    inside_libya = pd.Series(False, index=df.index)
    coordinate_rows = df['lat'].notna() & df['lon'].notna() & np.isfinite(df['lat']) & np.isfinite(df['lon'])
    boundary = _libya_boundary()
    inside_libya.loc[coordinate_rows] = [
        boundary.covers(Point(lon, lat))
        for lon, lat in zip(df.loc[coordinate_rows, 'lon'], df.loc[coordinate_rows, 'lat'])
    ]
    valid &= inside_libya
    rejected = raw.loc[~valid].copy()
    rejected['rejection_reason'] = 'Invalid identity, non-606 MCC, invalid coordinate, or outside supplied Libya boundary'
    df = df.loc[valid].copy()
    for col in ['mcc', 'net', 'area', 'cell']:
        df[col] = df[col].astype('int64')
    now = pd.Timestamp.now(tz='UTC') if as_of is None else pd.Timestamp(as_of)
    now = now.tz_localize('UTC') if now.tzinfo is None else now.tz_convert('UTC')
    for col in ['created', 'updated']:
        df[col + '_utc'] = pd.to_datetime(df[col], unit='s', errors='coerce', utc=True)
    df['timestamp_valid'] = (
        (df['created'] > 0) & (df['updated'] >= df['created'])
        & df['created_utc'].notna() & df['updated_utc'].notna()
        & (df['updated_utc'] <= now)
    )
    df['age_days'] = (now - df['updated_utc']).dt.total_seconds() / 86400
    df['review_eligible'] = (
        df['timestamp_valid'] & df['samples'].ge(2) & np.isfinite(df['samples'])
        & (df['samples'] % 1 == 0) & df['age_days'].between(0, 730)
    )
    before = len(df)
    # Prefer valid timestamps, then the most recently updated snapshot of a cell.
    df = df.sort_values(['timestamp_valid', 'updated', 'samples'], na_position='first', kind='stable')
    df = df.drop_duplicates(IDENTITY, keep='last').sort_values(IDENTITY).reset_index(drop=True)
    df['operator'] = df['net'].map({0: 'Libyana', 1: 'Al-Madar'}).fillna('Unknown')
    df['unit_semantics'] = df['radio'].map({'UMTS': 'PSC', 'LTE': 'PCI'}).fillna('not_applicable')
    df['range_is_estimated'] = True
    df['source'] = 'OpenCellID'
    report = {
        'source': source, 'as_of_utc': now.isoformat(),
        'input_rows': len(raw), 'rejected_rows': len(rejected),
        'duplicate_identity_rows': before - len(df), 'retained_cells': len(df),
        'operator_counts': df['operator'].value_counts().to_dict(),
        'radio_counts': df['radio'].value_counts().to_dict(),
        'invalid_timestamp_cells': int((~df['timestamp_valid']).sum()),
        'review_eligible_cells': int(df['review_eligible'].sum()),
        'unexpected_changeable_values': int(df['changeable'].ne(1).fillna(True).sum()),
        'unexpected_average_signal_values': int(df['averageSignal'].ne(0).fillna(True).sum()),
        'review_policy': 'At least 2 samples, valid timestamps, updated within 730 days; proximity is not proof of coverage.',
        'column_semantics': {
            'unit': 'PSC for UMTS, PCI for LTE; empty/not applicable for GSM and CDMA.',
            'range': 'Estimated cell range in meters; not a coverage radius or positional accuracy.',
            'changeable': 'Deprecated and excluded from decisions.',
            'averageSignal': 'Deprecated and excluded from decisions.',
        },
        'spatial_scope': 'Supplied OCHA Libya admin-0 boundary.',
        'attribution': 'OpenCellID https://opencellid.org/; https://docs.opencellid.org/docs/downloads/database-format',
    }
    return df, rejected, report


@lru_cache(maxsize=1)
def _libya_boundary():
    """Load the supplied national boundary once in WGS84."""
    return gpd.read_file(ADMIN0_GEOJSON_PATH).to_crs(CRS_WGS84).geometry.union_all()


def projected(lons, lats):
    transformer = Transformer.from_crs('EPSG:4326', CRS_PROJECTED_LIBYA, always_xy=True)
    return np.column_stack(transformer.transform(np.asarray(lons), np.asarray(lats)))


def annotate_candidates(candidates, cells=None):
    """Add observation proximity for review without changing priority ranks."""
    result = candidates.copy()
    distance_columns = [
        'opencellid_any_distance_m',
        'opencellid_recent_distance_m',
        'opencellid_libyana_distance_m',
        'opencellid_almadar_distance_m',
    ]
    for column in distance_columns:
        result[column] = np.nan
    result['opencellid_review_required'] = False
    if cells is None:
        cells, _ = import_pipeline()
    if result.empty:
        return result
    coords = projected(result['canonical_longitude'], result['canonical_latitude'])
    eligible = cells[cells['review_eligible']].copy()
    groups = {'any': cells, 'recent': eligible,
              'libyana': eligible[eligible['net'] == 0],
              'almadar': eligible[eligible['net'] == 1]}
    for label, subset in groups.items():
        col = f'opencellid_{label}_distance_m'
        if not subset.empty and len(result):
            tree = cKDTree(projected(subset['lon'], subset['lat']))
            distances, _ = tree.query(coords)
            result[col] = np.round(distances, 1)
    result['opencellid_review_required'] = result['opencellid_recent_distance_m'].le(3000)
    return result


def import_pipeline(path: Path | None = None):
    """Validate the supplied export and return its in-memory cells and report."""
    if path is not None:
        cells, rejected, report = load_cells(path)
    else:
        from antenna_cell_placement.config import DATA_DIR
        paths = [OPENCELLID_RAW_PATH, DATA_DIR / 'new_data/libya_antennas/opencellid_libya.csv']
        frames, reports, rejects = [], [], []
        for source_path in paths:
            if source_path.exists():
                frame, bad, summary = load_cells(source_path)
                frames.append(frame[COLUMNS])
                reports.append(summary)
                rejects.append(bad)
        if not frames:
            raise FileNotFoundError('No declared OpenCellID exports found')
        cells, _, report = _validate_cells(pd.concat(frames, ignore_index=True), 'Merged declared OpenCellID exports')
        rejected = pd.concat(rejects, ignore_index=True)
        report['sources'] = reports
        report['input_rows'] = sum(r['input_rows'] for r in reports)
        report['rejected_rows'] = len(rejected)
        report['duplicate_identity_rows'] = report['input_rows'] - len(rejected) - len(cells)
    report['rejected_preview'] = rejected.head(5).to_dict(orient='records')
    return cells, report
