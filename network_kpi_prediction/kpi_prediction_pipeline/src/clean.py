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

from src.config import KPI_CONFIG, KPI_KEYS, CARRIER_BANDS, apply_bounds


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


def load_clean_data(data_path: str = None) -> pd.DataFrame:
    """Convenience loader resolving carrier_ran_kpi_clean.csv from standard data paths."""
    if data_path and os.path.exists(data_path):
        resolved = data_path
    else:
        candidates = [
            os.path.join(_REPO_ROOT, 'data', 'carrier_ran_kpi_clean.csv'),
            os.path.join(_REPO_ROOT, 'carrier_ran_kpi_clean.csv'),
            os.path.join(_REPO_ROOT, 'data', 'carrier_kpi_clean.csv'),
            os.path.join(_REPO_ROOT, 'carrier_kpi_clean.csv')
        ]
        resolved = next((p for p in candidates if os.path.exists(p)), candidates[0])

    if not os.path.exists(resolved):
        raise FileNotFoundError(f"Telemetry file '{resolved}' not found.")

    df = pd.read_csv(resolved)
    return clean_telemetry(df)
