"""
src/split.py
Chronological Train / Validation / Test Splitting Engine for Time Series Telemetry.
Enforces strict temporal ordering (no lookahead bias or data leakage).
"""

import os
import json
from typing import Dict, Any, Tuple
import pandas as pd
import numpy as np

def split_carrier_data(
    df: pd.DataFrame,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    test_ratio: float = 0.15,
    date_col: str = 'date',
    carrier_col: str = 'carrier_freq'
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """
    Performs strict chronological 3-way splitting (Train / Val / Test) per carrier band.
    
    Args:
        df: Raw telemetry DataFrame.
        train_ratio: Fraction of historical data for training (default 0.70).
        val_ratio: Fraction of historical data for validation/tuning (default 0.15).
        test_ratio: Fraction of historical data for holdout testing (default 0.15).
        date_col: Name of datetime column.
        carrier_col: Name of carrier identifier column.
        
    Returns:
        (train_df, val_df, test_df, manifest_dict)
    """
    assert np.isclose(train_ratio + val_ratio + test_ratio, 1.0), \
        f"Split ratios must sum to 1.0 (got {train_ratio + val_ratio + test_ratio})"

    df_clean = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df_clean[date_col]):
        df_clean[date_col] = pd.to_datetime(df_clean[date_col])

    train_list = []
    val_list = []
    test_list = []
    manifest: Dict[str, Any] = {
        'ratios': {
            'train': train_ratio,
            'val': val_ratio,
            'test': test_ratio
        },
        'carriers': {}
    }

    carrier_groups = df_clean.groupby(carrier_col)
    for carrier, sub in carrier_groups:
        sub_sorted = sub.sort_values(date_col).reset_index(drop=True)
        n = len(sub_sorted)
        
        n_train = int(np.round(n * train_ratio))
        n_val = int(np.round(n * val_ratio))
        # Ensure test gets the remaining rows to preserve total count exactly
        n_test = n - (n_train + n_val)
        
        # Edge case safeguard
        if n_test <= 0:
            n_test = 1
            n_train = n - n_val - n_test

        train_part = sub_sorted.iloc[:n_train].copy()
        val_part = sub_sorted.iloc[n_train:n_train + n_val].copy()
        test_part = sub_sorted.iloc[n_train + n_val:].copy()

        # Strict chronological verification
        assert len(train_part) + len(val_part) + len(test_part) == n, \
            f"Row count mismatch for carrier {carrier}: {len(train_part)} + {len(val_part)} + {len(test_part)} != {n}"
        
        if len(val_part) > 0 and len(train_part) > 0:
            assert train_part[date_col].max() < val_part[date_col].min(), \
                f"Temporal leak: Train max date ({train_part[date_col].max()}) >= Val min date ({val_part[date_col].min()})"
        
        if len(test_part) > 0 and len(val_part) > 0:
            assert val_part[date_col].max() < test_part[date_col].min(), \
                f"Temporal leak: Val max date ({val_part[date_col].max()}) >= Test min date ({test_part[date_col].min()})"

        train_list.append(train_part)
        val_list.append(val_part)
        test_list.append(test_part)

        manifest['carriers'][str(carrier)] = {
            'total_rows': n,
            'train': {
                'count': len(train_part),
                'start_date': train_part[date_col].min().strftime('%Y-%m-%d'),
                'end_date': train_part[date_col].max().strftime('%Y-%m-%d'),
                'pct': round(len(train_part) / n * 100, 2)
            },
            'val': {
                'count': len(val_part),
                'start_date': val_part[date_col].min().strftime('%Y-%m-%d'),
                'end_date': val_part[date_col].max().strftime('%Y-%m-%d'),
                'pct': round(len(val_part) / n * 100, 2)
            },
            'test': {
                'count': len(test_part),
                'start_date': test_part[date_col].min().strftime('%Y-%m-%d'),
                'end_date': test_part[date_col].max().strftime('%Y-%m-%d'),
                'pct': round(len(test_part) / n * 100, 2)
            }
        }

    train_df = pd.concat(train_list, ignore_index=True)
    val_df = pd.concat(val_list, ignore_index=True)
    test_df = pd.concat(test_list, ignore_index=True)

    manifest['summary'] = {
        'total_rows': len(df_clean),
        'train_rows': len(train_df),
        'val_rows': len(val_df),
        'test_rows': len(test_df),
        'train_pct': round(len(train_df) / len(df_clean) * 100, 2),
        'val_pct': round(len(val_df) / len(df_clean) * 100, 2),
        'test_pct': round(len(test_df) / len(df_clean) * 100, 2)
    }

    return train_df, val_df, test_df, manifest

def export_splits(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    manifest: Dict[str, Any],
    output_dir: str = 'data/splits'
) -> Dict[str, str]:
    """
    Saves the split datasets and manifest to disk.
    """
    os.makedirs(output_dir, exist_ok=True)
    paths = {
        'train': os.path.join(output_dir, 'train.csv'),
        'val': os.path.join(output_dir, 'val.csv'),
        'test': os.path.join(output_dir, 'test.csv'),
        'manifest': os.path.join(output_dir, 'split_manifest.json')
    }

    train_df.to_csv(paths['train'], index=False)
    val_df.to_csv(paths['val'], index=False)
    test_df.to_csv(paths['test'], index=False)

    with open(paths['manifest'], 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)

    return paths

def load_splits(input_dir: str = 'data/splits') -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """
    Loads saved split datasets and manifest from disk.
    """
    train_df = pd.read_csv(os.path.join(input_dir, 'train.csv'))
    val_df = pd.read_csv(os.path.join(input_dir, 'val.csv'))
    test_df = pd.read_csv(os.path.join(input_dir, 'test.csv'))
    
    with open(os.path.join(input_dir, 'split_manifest.json'), 'r', encoding='utf-8') as f:
        manifest = json.load(f)

    return train_df, val_df, test_df, manifest
