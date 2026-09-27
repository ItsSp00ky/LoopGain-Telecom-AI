"""features.py: Feature engineering pipeline for time-series forecasting.
Generates calendar/cyclical signals, weekly lags, rolling window statistics, and momentum indicators.
Strictly ensures zero target leakage using shifted past windows.
"""

from pathlib import Path
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler

_PKG_ROOT = Path(__file__).resolve().parent.parent


def create_time_features(
    df: pd.DataFrame,
    target_col: str = "kpi_volume_gb",
    lags: list[int] | None = None,
    rolling_windows: list[int] | None = None,
) -> pd.DataFrame:
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
    if lags is None:
        lags = [1, 2, 3, 7, 14, 21, 28]
    target_series = df[target_col]
    for lag in lags:
        df[f"lag_{lag}"] = target_series.shift(lag)

    # 3. Rolling Window Statistics (computed on shift(1) to strictly prevent lookahead)
    if rolling_windows is None:
        rolling_windows = [7, 14, 28]
    shifted = target_series.shift(1)
    for w in rolling_windows:
        min_p = max(1, w // 2)
        df[f"rolling_mean_{w}"] = shifted.rolling(window=w, min_periods=min_p).mean()
        df[f"rolling_std_{w}"] = shifted.rolling(window=w, min_periods=min_p).std().fillna(0)
    if 7 in rolling_windows:
        df["rolling_min_7"] = shifted.rolling(window=7, min_periods=3).min()
        df["rolling_max_7"] = shifted.rolling(window=7, min_periods=3).max()

    # 4. Momentum & Relative Growth Differences
    df["diff_1"] = df["lag_1"] - df["lag_2"] if "lag_2" in df else (df["lag_1"] - target_series.shift(2))
    df["diff_7"] = df["lag_1"] - (df["lag_8"] if "lag_8" in df else target_series.shift(8))
    short_w = rolling_windows[0] if rolling_windows else 7
    long_w = rolling_windows[-1] if rolling_windows else 28
    df[f"ratio_{short_w}_{long_w}"] = df.get(f"rolling_mean_{short_w}", shifted) / (df.get(f"rolling_mean_{long_w}", shifted) + 1e-6)

    # Drop rows with NaN from initial lag window
    warmup_days = max(lags) if lags else 28
    initial_len = len(df)
    df = df.dropna().reset_index(drop=True)
    dropped_rows = initial_len - len(df)
    print(f"[Features] Created {df.shape[1] - 2} features. Dropped {dropped_rows} warmup rows for lag window ({warmup_days} days).")

    return df


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    """Returns the list of predictive feature column names, excluding metadata and targets."""
    excluded = {"date", "kpi_volume_gb", "kpi_volume_gb_raw", "is_anomaly"}
    return [c for c in df.columns if c not in excluded]


def resolve_clean_traffic_file(clean_csv: str | Path | None = None) -> Path:
    """Dynamically resolves clean traffic dataset path."""
    if clean_csv:
        p = Path(clean_csv)
        if p.exists():
            return p
        if (_PKG_ROOT / clean_csv).exists():
            return _PKG_ROOT / clean_csv

    candidates = [
        _PKG_ROOT / "data" / "traffic_kpi_clean.csv",
        _PKG_ROOT.parent / "data" / "traffic_kpi_clean.csv",
        Path("data/traffic_kpi_clean.csv"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def prepare_datasets(
    clean_csv: str | Path | None = None,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    lags: list[int] | None = None,
    rolling_windows: list[int] | None = None,
) -> tuple[dict, StandardScaler, list[str]]:
    """Loads clean data, builds features, splits chronologically, and fits scaler ONLY on train."""
    resolved_csv = resolve_clean_traffic_file(clean_csv)
    if not resolved_csv.exists():
        raise FileNotFoundError(f"Clean traffic dataset not found at: {resolved_csv}")

    raw_df = pd.read_csv(resolved_csv)
    cols = [c.strip().strip('"') for c in raw_df.columns]
    if "date" not in cols:
        from src.data_cleaning import run_clean_pipeline
        raw_df = run_clean_pipeline(raw_path=resolved_csv)
    else:
        raw_df["date"] = pd.to_datetime(raw_df["date"])

    featured_df = create_time_features(
        raw_df, target_col="kpi_volume_gb", lags=lags, rolling_windows=rolling_windows
    )
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
