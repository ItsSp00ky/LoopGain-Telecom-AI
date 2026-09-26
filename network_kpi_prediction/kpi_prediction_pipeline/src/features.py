"""
src/features.py
Mathematical Feature Engineering for Cellular KPI Time-Series Projections.
Implements orthogonal Fourier harmonics, asymptotically bounded damped trends,
and calendar periodicity while strictly eliminating multicollinear redundancies.
"""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from typing import List, Tuple
import numpy as np
import pandas as pd

def compute_damped_trend(t_days: np.ndarray, phi: float = 0.5) -> np.ndarray:
    """
    Computes an asymptotically saturating damped trend:
    trend(t) = (1 - exp(-phi * (t / 365.25))) / phi
    Guarantees that 365-day forward extrapolations cannot mathematically diverge.
    """
    t_years = t_days / 365.25
    return (1.0 - np.exp(-phi * t_years)) / phi

def extract_time_features(df: pd.DataFrame, base_date: pd.Timestamp = None) -> pd.DataFrame:
    """
    Extracts continuous time index, non-redundant Fourier series,
    and calendar signals from datetime column.
    """
    df = df.copy()
    if not np.issubdtype(df['date'].dtype, np.datetime64):
        df['date'] = pd.to_datetime(df['date'])
        
    if base_date is None:
        base_date = df['date'].min()
        
    # Unbroken continuous elapsed days
    df['t'] = (df['date'] - base_date).dt.total_seconds() / 86400.0
    
    # 1. Asymptotically Bounded Damped Trend (Pure Asymptotic Damping, Zero Linear Extrapolation)
    df['trend_damped'] = compute_damped_trend(df['t'].values, phi=0.4)
    
    # 2. Orthogonal Annual Fourier Harmonics (T = 365.25 days, k = 1, 2, 3)
    for k in range(1, 4):
        omega = 2.0 * np.pi * k / 365.25
        df[f'annual_sin_k{k}'] = np.sin(omega * df['t'])
        df[f'annual_cos_k{k}'] = np.cos(omega * df['t'])
        
    # 3. Orthogonal Weekly Fourier Harmonics (T = 7.0 days, k = 1, 2)
    for k in range(1, 3):
        omega = 2.0 * np.pi * k / 7.0
        df[f'weekly_sin_k{k}'] = np.sin(omega * df['t'])
        df[f'weekly_cos_k{k}'] = np.cos(omega * df['t'])
        
    # 4. Month Cyclical Encoding (T = 12 months)
    month = df['date'].dt.month
    df['month_sin'] = np.sin(2.0 * np.pi * month / 12.0)
    df['month_cos'] = np.cos(2.0 * np.pi * month / 12.0)
    
    # 5. Network Traffic Indicators (Business Day vs Weekend Diurnal Load & Holidays)
    dow = df['date'].dt.dayofweek
    df['is_weekend'] = (dow >= 5).astype(float)
    df['midweek_peak'] = ((dow >= 1) & (dow <= 3)).astype(float)
    df['is_holiday'] = compute_holiday_indicators(df['date'])
    
    return df

def compute_holiday_indicators(dates: pd.Series) -> np.ndarray:
    """
    Computes binary flag for major public and telecom peak holidays where mobile traffic
    shifts drastically between commercial cell sectors and residential macro tiers.
    """
    dt = pd.to_datetime(dates)
    m = dt.dt.month
    d = dt.dt.day
    dow = dt.dt.dayofweek
    
    # Fixed date holidays: New Year (Jan 1), Independence (Jul 4), Christmas Eve/Day (Dec 24-25), NYE (Dec 31)
    is_fixed = (
        ((m == 1) & (d == 1)) |
        ((m == 7) & (d == 4)) |
        ((m == 12) & (d == 24)) |
        ((m == 12) & (d == 25)) |
        ((m == 12) & (d == 31))
    )
    # Floating holidays:
    is_memorial = (m == 5) & (dow == 0) & (d >= 25)
    is_labor = (m == 9) & (dow == 0) & (d <= 7)
    is_thanksgiving = (m == 11) & (dow == 3) & (d >= 22) & (d <= 28)
    
    return (is_fixed | is_memorial | is_labor | is_thanksgiving).astype(float).values

def compute_autoregressive_features(y_trans: np.ndarray) -> np.ndarray:
    """
    Computes autoregressive lag and rolling volatility features in transformed space.
    Strictly uses shift(1) to guarantee zero forward lookahead data leakage.
    Returns matrix of shape (n_samples, 4): [lag_1, lag_7, roll_mean_7d, roll_std_7d].
    """
    s = pd.Series(y_trans)
    lag_1 = s.shift(1).bfill().values
    lag_7 = s.shift(7).bfill().values
    roll_mean_7 = s.shift(1).rolling(7, min_periods=1).mean().bfill().values
    roll_std_7 = s.shift(1).rolling(7, min_periods=1).std().fillna(0.0).values
    return np.column_stack([lag_1, lag_7, roll_mean_7, roll_std_7])

def get_base_feature_columns() -> List[str]:
    """Returns the ordered list of continuous and cyclical model feature names (no linear trend)."""
    cols = ['trend_damped']
    cols += [f'annual_sin_k{k}' for k in range(1, 4)] + [f'annual_cos_k{k}' for k in range(1, 4)]
    cols += [f'weekly_sin_k{k}' for k in range(1, 3)] + [f'weekly_cos_k{k}' for k in range(1, 3)]
    cols += ['month_sin', 'month_cos', 'is_weekend', 'midweek_peak', 'is_holiday']
    return cols

def get_feature_columns() -> List[str]:
    """Returns the ordered list of continuous and cyclical model feature names (purged of trend_linear)."""
    return get_base_feature_columns()

def get_ar_feature_columns() -> List[str]:
    """Returns the ordered list of autoregressive and rolling volatility feature names."""
    return ['lag_1', 'lag_7', 'roll_mean_7d', 'roll_std_7d']

def get_all_feature_columns() -> List[str]:
    """Returns complete combined feature column names."""
    return get_base_feature_columns() + get_ar_feature_columns()
