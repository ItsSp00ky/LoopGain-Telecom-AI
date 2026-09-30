import pandas as pd
import numpy as np
from typing import List, Tuple

class TimeSeriesFeatureEngineer:
    """
    Leak-Free Feature Engineering for Panel Time-Series Forecasting.
    Constructs lags, rolling statistics, calendar embeddings, and site baselines.
    """
    
    @staticmethod
    def add_calendar_features(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
        """Extracts deterministic temporal signals and cyclical encodings."""
        features = []
        df['dow'] = df['Date'].dt.dayofweek
        df['is_libya_weekend'] = df['dow'].isin([4, 5]).astype(int)  # Friday (4) / Saturday (5)
        df['day'] = df['Date'].dt.day
        df['month'] = df['Date'].dt.month
        df['sin_dow'] = np.sin(2 * np.pi * df['dow'] / 7)
        df['cos_dow'] = np.cos(2 * np.pi * df['dow'] / 7)
        df['sin_month'] = np.sin(2 * np.pi * df['month'] / 12)
        df['cos_month'] = np.cos(2 * np.pi * df['month'] / 12)
        df['tower_num'] = df['ERBS Id'].str.replace('TWR_', '').astype(int)
        
        features.extend(['dow', 'is_libya_weekend', 'day', 'month', 'sin_dow', 'cos_dow', 'sin_month', 'cos_month', 'tower_num'])
        return df, features

    @staticmethod
    def add_temporal_kpi_features(
        df: pd.DataFrame, target_col: str, kpi_prefix: str, cutoff_date: pd.Timestamp
    ) -> Tuple[pd.DataFrame, List[str]]:
        """
        Generates leak-free lag and rolling statistics for a given KPI.
        Strictly applies .shift(1) to avoid target leakage into predictors.
        """
        features = []
        g = df.groupby('ERBS Id')[target_col]
        
        # 1. Multi-Horizon Autoregressive Lags
        for lag in [1, 2, 3, 7, 14, 21, 28]:
            col_name = f"{kpi_prefix}_lag_{lag}"
            df[col_name] = g.shift(lag)
            features.append(col_name)
            
        # 2. Moving Statistics (Shifted by 1)
        df[f"{kpi_prefix}_roll_mean_7"] = g.transform(lambda x: x.shift(1).rolling(7, min_periods=1).mean())
        df[f"{kpi_prefix}_roll_std_7"] = g.transform(lambda x: x.shift(1).rolling(7, min_periods=1).std()).fillna(0)
        df[f"{kpi_prefix}_roll_mean_14"] = g.transform(lambda x: x.shift(1).rolling(14, min_periods=1).mean())
        df[f"{kpi_prefix}_roll_mean_28"] = g.transform(lambda x: x.shift(1).rolling(28, min_periods=1).mean())
        df[f"{kpi_prefix}_diff_1_7"] = df[f"{kpi_prefix}_lag_1"] - df[f"{kpi_prefix}_lag_7"]
        
        features.extend([
            f"{kpi_prefix}_roll_mean_7",
            f"{kpi_prefix}_roll_std_7",
            f"{kpi_prefix}_roll_mean_14",
            f"{kpi_prefix}_roll_mean_28",
            f"{kpi_prefix}_diff_1_7"
        ])
        
        # 3. Static Historical Site Baselines (Calculated STRICTLY on Train Set)
        train_mask = df['Date'] < cutoff_date
        site_stats = df[train_mask].groupby('ERBS Id')[target_col].agg(['mean', 'std']).reset_index()
        site_stats.columns = ['ERBS Id', f"{kpi_prefix}_tower_mean", f"{kpi_prefix}_tower_std"]
        site_stats[f"{kpi_prefix}_tower_std"] = site_stats[f"{kpi_prefix}_tower_std"].fillna(0)
        
        df = df.merge(site_stats, on='ERBS Id', how='left')
        global_train_mean = df[train_mask][target_col].mean()
        df[f"{kpi_prefix}_tower_mean"] = df[f"{kpi_prefix}_tower_mean"].fillna(global_train_mean)
        df[f"{kpi_prefix}_tower_std"] = df[f"{kpi_prefix}_tower_std"].fillna(0)
        
        features.extend([f"{kpi_prefix}_tower_mean", f"{kpi_prefix}_tower_std"])
        return df, features
