"""features.py: Feature engineering pipeline for time-series forecasting.
Generates calendar/cyclical signals, weekly lags, rolling window statistics, and momentum indicators.
Strictly ensures zero target leakage using shifted past windows.
"""

import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler


def create_time_features(df: pd.DataFrame, target_col: str = "kpi_volume_gb") -> pd.DataFrame:
    """Generates comprehensive tabular time-series features from the contiguous KPI series.

    All lag and rolling statistics strictly use shift(1) to avoid lookahead leakage.
    """
    df = df.sort_values("date").copy().reset_index(drop=True)

    # 1. Calendar & Cyclical Features
    df["day_of_week"] = df["date"].dt.dayofweek
    df["is_weekend"] = df["day_of_week"].isin([5, 6]).astype(int)
    df["month"] = df["date"].dt.month
    df["day_of_month"] = df["date"].dt.day
    df["day_of_year"] = df["date"].dt.dayofyear
    df["week_of_year"] = df["date"].dt.isocalendar().week.astype(int)

    # Cyclical trigonometric transforms
    df["sin_dow"] = np.sin(2 * np.pi * df["day_of_week"] / 7.0)
    df["cos_dow"] = np.cos(2 * np.pi * df["day_of_week"] / 7.0)
    df["sin_doy"] = np.sin(2 * np.pi * df["day_of_year"] / 365.25)
    df["cos_doy"] = np.cos(2 * np.pi * df["day_of_year"] / 365.25)

    # Macro trend step (elapsed days from series start)
    start_date = df["date"].min()
    df["trend_step"] = (df["date"] - start_date).dt.days

    # 2. Lag Features (Shifted so row t only sees observations up to t-1)
    target_series = df[target_col]
    lags = [1, 2, 3, 7, 14, 21, 28]
    for lag in lags:
        df[f"lag_{lag}"] = target_series.shift(lag)

    # 3. Rolling Window Statistics (computed on shift(1) to strictly prevent lookahead)
    shifted = target_series.shift(1)
    df["rolling_mean_7"] = shifted.rolling(window=7, min_periods=3).mean()
    df["rolling_std_7"] = shifted.rolling(window=7, min_periods=3).std().fillna(0)
    df["rolling_min_7"] = shifted.rolling(window=7, min_periods=3).min()
    df["rolling_max_7"] = shifted.rolling(window=7, min_periods=3).max()

    df["rolling_mean_14"] = shifted.rolling(window=14, min_periods=7).mean()
    df["rolling_std_14"] = shifted.rolling(window=14, min_periods=7).std().fillna(0)

    df["rolling_mean_28"] = shifted.rolling(window=28, min_periods=14).mean()

    # 4. Momentum & Relative Growth Differences
    df["diff_1"] = df["lag_1"] - df["lag_2"]
    df["diff_7"] = df["lag_1"] - df["lag_8"] if "lag_8" in df else (df["lag_1"] - target_series.shift(8))
    df["ratio_7_28"] = df["rolling_mean_7"] / (df["rolling_mean_28"] + 1e-6)

    # Drop rows with NaN from initial lag window (first 28 days)
    # The remaining rows have full feature support
    initial_len = len(df)
    df = df.dropna().reset_index(drop=True)
    dropped_rows = initial_len - len(df)
    print(f"[Features] Created {df.shape[1] - 2} features. Dropped {dropped_rows} warmup rows for lag window (28 days).")

    return df


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """Returns the list of predictive feature column names, excluding metadata and targets."""
    excluded = {"date", "kpi_volume_gb", "kpi_volume_gb_raw", "is_anomaly"}
    return [c for c in df.columns if c not in excluded]


def prepare_datasets(
    clean_csv: str = "data/traffic_kpi_clean.csv",
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
) -> tuple[dict, StandardScaler, list[str]]:
    """Loads clean data, builds features, splits chronologically, and fits scaler ONLY on train."""
    raw_df = pd.read_csv(clean_csv)
    raw_df["date"] = pd.to_datetime(raw_df["date"])

    featured_df = create_time_features(raw_df, target_col="kpi_volume_gb")
    feature_cols = get_feature_columns(featured_df)

    n = len(featured_df)
    n_train = int(n * train_ratio)
    n_val = int(n * val_ratio)

    train_data = featured_df.iloc[:n_train].copy().reset_index(drop=True)
    val_data = featured_df.iloc[n_train : n_train + n_val].copy().reset_index(drop=True)
    test_data = featured_df.iloc[n_train + n_val :].copy().reset_index(drop=True)

    # Fit scaler ONLY on training data per ML best practices
    scaler = StandardScaler()
    scaler.fit(train_data[feature_cols])

    X_train_scaled = scaler.transform(train_data[feature_cols])
    X_val_scaled = scaler.transform(val_data[feature_cols])
    X_test_scaled = scaler.transform(test_data[feature_cols])

    datasets = {
        "train": {
            "df": train_data,
            "X": train_data[feature_cols],
            "X_scaled": X_train_scaled,
            "y": train_data["kpi_volume_gb"].values,
            "dates": train_data["date"].values,
        },
        "val": {
            "df": val_data,
            "X": val_data[feature_cols],
            "X_scaled": X_val_scaled,
            "y": val_data["kpi_volume_gb"].values,
            "dates": val_data["date"].values,
        },
        "test": {
            "df": test_data,
            "X": test_data[feature_cols],
            "X_scaled": X_test_scaled,
            "y": test_data["kpi_volume_gb"].values,
            "dates": test_data["date"].values,
        },
        "full_df": featured_df,
    }

    print(
        f"[Datasets] Train samples: {len(train_data)} ({train_data['date'].min().strftime('%Y-%m-%d')} to {train_data['date'].max().strftime('%Y-%m-%d')})"
    )
    print(
        f"[Datasets] Val samples:   {len(val_data)} ({val_data['date'].min().strftime('%Y-%m-%d')} to {val_data['date'].max().strftime('%Y-%m-%d')})"
    )
    print(
        f"[Datasets] Test samples:  {len(test_data)} ({test_data['date'].min().strftime('%Y-%m-%d')} to {test_data['date'].max().strftime('%Y-%m-%d')})"
    )
    print(f"[Datasets] Feature count: {len(feature_cols)} features: {feature_cols}")

    return datasets, scaler, feature_cols


if __name__ == "__main__":
    prepare_datasets()
