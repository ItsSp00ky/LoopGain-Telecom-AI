"""OpenCellID cell observations, kept separate from inferred physical mast sites."""

import json
from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree

from antenna_cell_placement.config import (
    OPENCELLID_RAW_PATH, OPENCELLID_CLEANED_PATH, OPENCELLID_REPORT_PATH,
    CLEANED_PHYSICAL_SITES_CSV, RECOMMENDATIONS_CSV, REPORTS_DIR,
    LIBYA_BBOX, CRS_PROJECTED_LIBYA, ADMIN0_GEOJSON_PATH, CRS_WGS84,
)

COLUMNS = 'radio mcc net area cell unit lon lat range samples changeable created updated averageSignal'.split()
IDENTITY = ['radio', 'mcc', 'net', 'area', 'cell']


def load_cells(path: Path, as_of=None):
    """Read headerless or named exports; quarantine invalid identity/location rows.

    Range is retained as source metadata, never used as a coverage radius or
    positional accuracy. Review eligibility is a configurable-in-code heuristic,
    not a measurement of confidence: >=2 samples and updated within 730 days.
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
    df = raw.copy()
    df['radio'] = df['radio'].str.strip().str.upper()
    for col in COLUMNS[1:]:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    valid = df['radio'].isin(['GSM', 'UMTS', 'LTE', 'CDMA', 'NR'])
    for col in ['mcc', 'net', 'area', 'cell']:
        valid &= df[col].notna() & np.isfinite(df[col]) & (df[col] >= 0) & (df[col] % 1 == 0)
    valid &= df['mcc'].eq(606)
    valid &= df['lat'].between(LIBYA_BBOX['min_lat'], LIBYA_BBOX['max_lat'])
    valid &= df['lon'].between(LIBYA_BBOX['min_lon'], LIBYA_BBOX['max_lon'])
    rejected = raw.loc[~valid].copy()
    rejected['rejection_reason'] = 'Invalid identity, non-606 MCC, or outside Libya bounding box'
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
    df['source'] = 'OpenCellID'
    report = {
        'source': str(path), 'as_of_utc': now.isoformat(),
        'input_rows': len(raw), 'rejected_rows': len(rejected),
        'duplicate_identity_rows': before - len(df), 'retained_cells': len(df),
        'operator_counts': df['operator'].value_counts().to_dict(),
        'radio_counts': df['radio'].value_counts().to_dict(),
        'invalid_timestamp_cells': int((~df['timestamp_valid']).sum()),
        'review_eligible_cells': int(df['review_eligible'].sum()),
        'review_policy': 'At least 2 samples, valid timestamps, updated within 730 days; proximity is not proof of coverage.',
        'spatial_scope': 'Libya bounding box; not a national boundary polygon.',
        'attribution': 'OpenCellID https://opencellid.org/; https://docs.opencellid.org/docs/downloads/database-format',
    }
    return df, rejected, report


def projected(lons, lats):
    transformer = Transformer.from_crs('EPSG:4326', CRS_PROJECTED_LIBYA, always_xy=True)
    return np.column_stack(transformer.transform(np.asarray(lons), np.asarray(lats)))


@lru_cache(maxsize=1)
def _libya_boundary():
    """Load the supplied national boundary once in WGS84."""
    return gpd.read_file(ADMIN0_GEOJSON_PATH).to_crs(CRS_WGS84).geometry.union_all()


def annotate_candidates(candidates, cells=None):
    """Add observation proximity for review without changing model inputs/ranks."""
    result = candidates.copy()
    if cells is None:
        if not OPENCELLID_RAW_PATH.exists():
            return result
        cells, _, _ = load_cells(OPENCELLID_RAW_PATH)
    coords = projected(result['canonical_longitude'], result['canonical_latitude'])
    eligible = cells[cells['review_eligible']].copy()
    groups = {'any': cells, 'recent': eligible,
              'libyana': eligible[eligible['net'] == 0],
              'almadar': eligible[eligible['net'] == 1]}
    for label, subset in groups.items():
        col = f'opencellid_{label}_distance_m'
        result[col] = np.nan
        if not subset.empty and len(result):
            tree = cKDTree(projected(subset['lon'], subset['lat']))
            distances, _ = tree.query(coords)
            result[col] = np.round(distances, 1)
    result['opencellid_review_required'] = result['opencellid_recent_distance_m'].le(3000)
    return result


def import_pipeline(path: Path = OPENCELLID_RAW_PATH):
    cells, rejected, report = load_cells(path)
    if CLEANED_PHYSICAL_SITES_CSV.exists() and not cells.empty:
        sites = pd.read_csv(CLEANED_PHYSICAL_SITES_CSV)
        if not sites.empty:
            tree = cKDTree(projected(sites['canonical_longitude'], sites['canonical_latitude']))
            distances, _ = tree.query(projected(cells['lon'], cells['lat']))
            cells['nearest_existing_site_m'] = np.round(distances, 1)
            report['cells_within_50m_of_existing_site'] = int((distances <= 50).sum())
            report['cells_over_3km_from_existing_site'] = int((distances > 3000).sum())
    OPENCELLID_CLEANED_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    cells.to_csv(OPENCELLID_CLEANED_PATH, index=False)
    rejected.to_csv(OPENCELLID_CLEANED_PATH.with_name('opencellid_rejected.csv'), index=False)
    if RECOMMENDATIONS_CSV.exists():
        reviewed = annotate_candidates(pd.read_csv(RECOMMENDATIONS_CSV), cells)
        reviewed.to_csv(REPORTS_DIR / 'opencellid_recommendation_review.csv', index=False)
        report['recommendations_reviewed'] = len(reviewed)
        report['recommendations_near_recent_cells'] = int(reviewed['opencellid_review_required'].sum())
    OPENCELLID_REPORT_PATH.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return cells, report
