"""
src/clean.py
Data Cleaning, Schema Validation, and Anomaly Sanitization for 3GPP Telemetry.
Enforces physical domain boundaries, drops redundant columns, and sanitizes nulls.
"""

import os
import sys
from typing import Dict, Any, Tuple
import numpy as np
import pandas as pd

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.kpi_config import (
    KPI_CONFIG, KPI_KEYS, CARRIER_BANDS, apply_bounds,
    ERBS_CARRIER_PREFIX_RULES, DEFAULT_CARRIER_BAND,
    RAW_COLUMN_TO_KPI_MAP, SECONDS_PER_DAY
)


def clean_telemetry(df: pd.DataFrame) -> pd.DataFrame:
    """
    Cleans raw carrier KPI telemetry:
    1. Parses dates and sorts chronologically.
    2. Drops redundant internal columns (e.g. 'dt', 't', index columns).
    3. Removes duplicate carrier-date entries.
    4. Handles missing values via forward fill within carrier groups.
    5. Clips all KPI values strictly within 3GPP physical domain boundaries.
    """
    df = df.copy()

    # 1. Parse and validate date
    if 'date' not in df.columns and 'dt' in df.columns:
        df['date'] = df['dt']
    if 'date' not in df.columns:
        raise ValueError("Telemetry DataFrame must contain a 'date' column.")
    df['date'] = pd.to_datetime(df['date'])

    # 2. Drop redundant columns
    redundant_cols = ['dt', 't', 'Unnamed: 0']
    for c in redundant_cols:
        if c in df.columns:
            df.drop(columns=[c], inplace=True)

    # 3. Sort chronologically per carrier
    if 'carrier_freq' in df.columns:
        df['carrier_freq'] = df['carrier_freq'].astype(int)
        df.sort_values(by=['carrier_freq', 'date'], inplace=True)
        df.drop_duplicates(subset=['carrier_freq', 'date'], keep='last', inplace=True)
    else:
        df.sort_values(by=['date'], inplace=True)
        df.drop_duplicates(subset=['date'], keep='last', inplace=True)

    # 4. Handle missing values and enforce 3GPP physical domain bounds
    for kpi in KPI_KEYS:
        if kpi in df.columns:
            # Interpolate or forward fill nulls
            if 'carrier_freq' in df.columns:
                df[kpi] = df.groupby('carrier_freq')[kpi].transform(
                    lambda s: s.ffill().bfill()
                )
            else:
                df[kpi] = df[kpi].ffill().bfill()

            # Enforce physical bounds [0, 100%], non-negative throughput, etc.
            df[kpi] = apply_bounds(df[kpi].values, kpi)

    df.reset_index(drop=True, inplace=True)
    return df


def validate_telemetry(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Validates health and completeness of cleaned telemetry dataset.
    Returns status dict with row counts, carrier bands, and date ranges.
    """
    report = {
        'total_rows': len(df),
        'carriers': [],
        'missing_values': int(df.isna().sum().sum()),
        'date_range': None
    }
    if not df.empty and 'date' in df.columns:
        report['date_range'] = {
            'start': df['date'].min().strftime('%Y-%m-%d'),
            'end': df['date'].max().strftime('%Y-%m-%d')
        }
    if 'carrier_freq' in df.columns:
        report['carriers'] = sorted(df['carrier_freq'].unique().tolist())

    return report


def map_erbs_to_carrier(
    erbs_id: Any,
    prefix_rules: list = None,
    default_band: int = None
) -> int:
    """
    Classifies raw cell base station identifiers into 3GPP spectrum frequency tiers
    using prefix matching rules defined in KPI_CONFIG (or supplied prefix_rules):
    - NT -> Band 350 MHz (Macro Regional Coverage Tier)
    - SUR, TLILM, COW, VIP, TS, SBR -> Band 400 MHz (Rural Sub-1GHz Cluster)
    - NSB, NSU -> Band 1556 MHz (Mid-Band FDD Urban Tier)
    - ZWY, ZW, PH -> Band 1700 MHz (AWS/PCS Uplink Tier)
    - NZW, ZAW, TR, T, TI -> Band 3500 MHz (C-Band Regional Capacity Tier)
    - Default (Small Cells, DAS, DOT, Core Towers) -> Band 6200 MHz (High-Throughput Small Cell / Micro Cluster)
    """
    if prefix_rules is None:
        prefix_rules = ERBS_CARRIER_PREFIX_RULES
    if default_band is None:
        default_band = DEFAULT_CARRIER_BAND

    s = str(erbs_id).strip()
    for prefixes, band in prefix_rules:
        if s.startswith(prefixes):
            return band
    return default_band


def ingest_raw_erbs_telemetry(raw_path: str = None, out_path: str = None, col_map: Dict[str, str] = None) -> pd.DataFrame:
    """
    Ingests raw ERBS cell-level telemetry (erbs_cell_kpi_full_year.csv),
    aggregates metrics per carrier frequency band and date, computes cluster downtime,
    enforces 3GPP physical boundaries, and exports the master clean dataset.
    """
    if raw_path is None:
        candidates = [
            os.path.join(_REPO_ROOT, '..', 'data', 'all the data', 'carrier_earfcndl_kpi_daily.csv'),
            os.path.join(_REPO_ROOT, '..', 'data', 'all the data', 'erbs_cell_kpi_full_year.csv'),
            os.path.join(_REPO_ROOT, '..', 'data', 'all the data', 'erbs_cell_kpi_summer_120d.csv'),
            os.path.join(_REPO_ROOT, '..', 'data', 'all the data', 'macro_network_kpis_daily.csv'),
        ]
        raw_path = next((p for p in candidates if os.path.exists(p)), candidates[0])

    if not os.path.exists(raw_path):
        raise FileNotFoundError(f"Raw ERBS telemetry file '{raw_path}' not found.")

    df = pd.read_csv(raw_path)
    df.columns = [c.strip().strip('"') for c in df.columns]

    date_col = next((c for c in df.columns if 'date' in c.lower()), 'Date')
    df['date'] = pd.to_datetime(df[date_col], format='%m/%d/%y', errors='coerce')
    if df['date'].isna().any():
        df['date'] = pd.to_datetime(df[date_col], errors='coerce')

    has_earfcndl = 'earfcndl' in df.columns
    has_erbs = any('erbs' in c.lower() for c in df.columns)

    if has_earfcndl:
        df['carrier_freq'] = pd.to_numeric(df['earfcndl'], errors='coerce').fillna(DEFAULT_CARRIER_BAND).astype(int)
    elif has_erbs:
        erbs_col = next((c for c in df.columns if 'erbs' in c.lower()), 'ERBS Id')
        df['carrier_freq'] = df[erbs_col].apply(map_erbs_to_carrier)
    else:
        df['carrier_freq'] = DEFAULT_CARRIER_BAND

    raw_col_map = col_map if col_map is not None else RAW_COLUMN_TO_KPI_MAP

    found_map = {}
    used_cols = set()
    # Prioritize exact column matches
    for raw_name, std_name in raw_col_map.items():
        matched = next((c for c in df.columns if c.strip().lower() == raw_name.lower() or c.strip().lower() == std_name.lower()), None)
        if matched and matched not in used_cols:
            df[matched] = pd.to_numeric(df[matched].astype(str).str.replace(',', '').str.strip(), errors='coerce')
            found_map[matched] = std_name
            used_cols.add(matched)

    # Fallback to substring matching for any unmapped
    for raw_name, std_name in raw_col_map.items():
        if std_name not in found_map.values():
            matched = next((c for c in df.columns if (raw_name.lower() in c.lower() or std_name.lower() in c.lower()) and c not in used_cols), None)
            if matched:
                df[matched] = pd.to_numeric(df[matched].astype(str).str.replace(',', '').str.strip(), errors='coerce')
                found_map[matched] = std_name
                used_cols.add(matched)

    agg_dict = {col: 'mean' for col in found_map.keys()}
    daily_carrier = df.groupby(['date', 'carrier_freq']).agg(agg_dict).reset_index()
    daily_carrier = daily_carrier.rename(columns=found_map)

    if 'downtime_sec' not in daily_carrier.columns:
        if has_erbs:
            erbs_col = next((c for c in df.columns if 'erbs' in c.lower()), 'ERBS Id')
            cell_counts = df.groupby(['date', 'carrier_freq'])[erbs_col].nunique().reset_index().rename(columns={erbs_col: 'active_cells'})
            daily_carrier = pd.merge(daily_carrier, cell_counts, on=['date', 'carrier_freq'])
            avail = daily_carrier.get('availability_pct', 100.0)
            daily_carrier['downtime_sec'] = SECONDS_PER_DAY * daily_carrier['active_cells'] * np.maximum(0.0, 1.0 - (avail / 100.0))
            daily_carrier = daily_carrier.drop(columns=['active_cells'], errors='ignore')
        else:
            avail = daily_carrier.get('availability_pct', 100.0)
            daily_carrier['downtime_sec'] = SECONDS_PER_DAY * np.maximum(0.0, 1.0 - (avail / 100.0))

    daily_carrier['dt'] = daily_carrier['date'].dt.strftime('%Y-%m-%d')
    daily_carrier['date'] = daily_carrier['dt']

    cleaned_df = clean_telemetry(daily_carrier)

    if out_path is None:
        out_path = os.path.join(_REPO_ROOT, 'data', 'carrier_ran_kpi_clean.csv')

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cleaned_df.to_csv(out_path, index=False)
    return cleaned_df


def load_clean_data(data_path: str = None) -> pd.DataFrame:
    """Convenience loader resolving carrier_ran_kpi_clean.csv from standard data paths."""
    if data_path:
        if os.path.exists(data_path):
            resolved = data_path
        elif os.path.exists(os.path.join(_REPO_ROOT, data_path)):
            resolved = os.path.join(_REPO_ROOT, data_path)
        else:
            resolved = data_path
    else:
        candidates = [
            os.path.join(_REPO_ROOT, 'data', 'carrier_ran_kpi_clean.csv'),
            os.path.join(_REPO_ROOT, 'carrier_ran_kpi_clean.csv'),
            os.path.join(_REPO_ROOT, 'data', 'carrier_kpi_clean.csv'),
            os.path.join(_REPO_ROOT, 'carrier_kpi_clean.csv'),
            os.path.join(_REPO_ROOT, '..', 'data', 'carrier_ran_kpi_clean.csv'),
        ]
        resolved = next((p for p in candidates if os.path.exists(p)), candidates[0])

    if not os.path.exists(resolved):
        # Auto-ingest raw ERBS telemetry if available
        raw_candidates = [
            os.path.join(_REPO_ROOT, '..', 'data', 'all the data', 'carrier_earfcndl_kpi_daily.csv'),
            os.path.join(_REPO_ROOT, '..', 'data', 'all the data', 'erbs_cell_kpi_full_year.csv'),
            os.path.join(_REPO_ROOT, '..', 'data', 'all the data', 'erbs_cell_kpi_summer_120d.csv'),
            os.path.join(_REPO_ROOT, '..', 'data', 'all the data', 'macro_network_kpis_daily.csv'),
        ]
        raw_found = next((p for p in raw_candidates if os.path.exists(p)), None)
        if raw_found:
            return ingest_raw_erbs_telemetry(raw_found, resolved)
        raise FileNotFoundError(f"Telemetry file '{resolved}' not found.")

    sample = pd.read_csv(resolved, nrows=5)
    sample_cols = [c.strip().strip('"').lower() for c in sample.columns]
    is_already_clean = ('date' in sample_cols or 'dt' in sample_cols) and ('carrier_freq' in sample_cols)
    if not is_already_clean:
        return ingest_raw_erbs_telemetry(resolved)

    df = pd.read_csv(resolved)
    return clean_telemetry(df)
