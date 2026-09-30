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


def resolve_macro_kpis_file(macro_csv: str | Path | None = None) -> Path:
    """Dynamically resolves macro network KPIs dataset path."""
    if macro_csv:
        p = Path(macro_csv)
        if p.exists():
            return p
        if (_PKG_ROOT / macro_csv).exists():
            return _PKG_ROOT / macro_csv

    candidates = [
        _PKG_ROOT.parent / "data" / "macro_network_kpis_daily.csv",
        _PKG_ROOT / "data" / "macro_network_kpis_daily.csv",
        Path("data/macro_network_kpis_daily.csv"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def resolve_carrier_kpis_file(carrier_csv: str | Path | None = None) -> Path:
    """Dynamically resolves the per-band carrier KPI dataset path."""
    if carrier_csv:
        p = Path(carrier_csv)
        if p.exists():
            return p
        if (_PKG_ROOT / carrier_csv).exists():
            return _PKG_ROOT / carrier_csv

    candidates = [
        _PKG_ROOT.parent / "data" / "carrier_earfcndl_kpi_daily.csv",
        _PKG_ROOT / "data" / "carrier_earfcndl_kpi_daily.csv",
        Path("data/carrier_earfcndl_kpi_daily.csv"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def aggregate_carrier_kpis_daily(carrier_csv: str | Path | None = None) -> pd.DataFrame:
    """Collapses the per-band carrier export to one network-wide row per day.

    `macro_network_kpis_daily.csv` (already merged elsewhere in this module) has no
    availability, connected-user or downtime column at all - those only exist in the
    per-band carrier export. A simple mean across the 6 bands is used, matching how
    close a plain per-band mean already tracks the project's own pre-aggregated macro
    file for the KPIs both files share (checked directly: same-day RRC Setup Success
    Rate differs by 0.01 between a simple band mean and the macro file's own value).
    `pmCellDowntimeMan` is a band-cluster total in cell-seconds (see
    `cellular_kpi_forecast/src/kpi_config.py`), and bands have very different cell
    counts (9 to 667), so a plain mean across bands is not a per-cell duration; it is
    kept as a relative signal (`network_cell_downtime_raw`).
    """
    path = Path(carrier_csv) if carrier_csv else resolve_carrier_kpis_file()
    if not path.exists():
        raise FileNotFoundError(f"Carrier KPI dataset not found at: {path}")

    carrier_df = pd.read_csv(path)
    carrier_df = carrier_df.rename(columns={
        "Date": "date",
        "4G Cell Av. (%)": "network_availability_pct",
        "Avg RRC Connected users": "network_avg_connected_users",
        "pmCellDowntimeMan": "network_cell_downtime_raw",
    })
    daily = (
        carrier_df.groupby("date")[
            ["network_availability_pct", "network_avg_connected_users", "network_cell_downtime_raw"]
        ]
        .mean()
        .reset_index()
    )
    daily["date"] = pd.to_datetime(daily["date"])
    return daily


def prepare_multivariate_datasets(
    clean_csv: str | Path | None = None,
    macro_csv: str | Path | None = None,
    carrier_csv: str | Path | None = None,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    lags: list[int] | None = None,
    rolling_windows: list[int] | None = None,
    exo_subset: list[str] | None = None,
) -> tuple[dict, StandardScaler, list[str]]:
    """Merges traffic volume with every network KPI this module has, as exogenous features.

    `exo_subset` restricts which exogenous KPIs become features (for ablation on the
    exact same rows); by default all of them are used.

    Strictly uses shift(1) (and a 7-day rolling mean of the shifted series) on every
    radio metric to eliminate lookahead leakage while enriching traffic load modeling:
    DL/UL throughput, E-RAB drop rate, E-RAB establishment success rate, RRC setup
    success rate, handover success rate (from the daily macro export), plus network
    availability, average connected users and cell downtime (aggregated from the
    per-band carrier export - see `aggregate_carrier_kpis_daily`). The raw exogenous
    columns are kept in the returned frames (needed to recursively forecast them
    forward - see `forecast_future`'s `exo_cols`) but excluded from `feature_cols`,
    so the model itself only ever sees the shifted, leakage-safe versions.
    """
    resolved_clean = resolve_clean_traffic_file(clean_csv)
    resolved_macro = resolve_macro_kpis_file(macro_csv)

    if not resolved_macro.exists():
        raise FileNotFoundError(f"Macro KPI dataset not found at: {resolved_macro}")

    raw_df = pd.read_csv(resolved_clean)
    if "date" not in [c.strip().strip('"') for c in raw_df.columns]:
        from src.data_cleaning import run_clean_pipeline
        raw_df = run_clean_pipeline(raw_path=resolved_clean)
    else:
        raw_df["date"] = pd.to_datetime(raw_df["date"])

    macro_df = pd.read_csv(resolved_macro)
    macro_df = macro_df.rename(columns={
        "Date": "date",
        "RRC Setup Success Rate": "macro_rrc_setup_sr",
        "E-RAB Establishment Success Rate": "macro_erab_estab_sr",
        "E-RAB Drop Rate": "macro_erab_drop_rate",
        "Handover Success Rate ( 4G Intra System)": "macro_handover_sr_intra4g",
        "Handover Success Rate": "macro_handover_sr",
        "E-UTRAN IP Throughput UE DL": "macro_dl_throughput_mbps",
        "E-UTRAN IP Throughput UE UL": "macro_ul_throughput_mbps",
    })
    macro_df["date"] = pd.to_datetime(macro_df["date"])

    merged_df = pd.merge(raw_df, macro_df, on="date", how="inner")

    carrier_daily = aggregate_carrier_kpis_daily(carrier_csv)
    merged_df = pd.merge(merged_df, carrier_daily, on="date", how="inner")
    merged_df = merged_df.sort_values("date").reset_index(drop=True)

    # 1. Base Time & Target Lag Features
    featured_df = create_time_features(
        merged_df, target_col="kpi_volume_gb", lags=lags, rolling_windows=rolling_windows
    )

    # 2. Exogenous Network Features strictly on shift(1)
    exo_cols = [
        "macro_dl_throughput_mbps", "macro_ul_throughput_mbps",
        "macro_erab_drop_rate", "macro_erab_estab_sr",
        "macro_rrc_setup_sr", "macro_handover_sr", "macro_handover_sr_intra4g",
        "network_availability_pct", "network_avg_connected_users", "network_cell_downtime_raw",
    ]
    if exo_subset is not None:
        unknown = set(exo_subset) - set(exo_cols)
        if unknown:
            raise ValueError(f"Unknown exogenous KPIs: {sorted(unknown)}")
        exo_cols = [c for c in exo_cols if c in exo_subset]
    for c in exo_cols:
        if c in featured_df.columns:
            s = featured_df[c].shift(1)
            featured_df[f"exo_{c}_lag1"] = s
            featured_df[f"exo_{c}_roll7"] = s.rolling(window=7, min_periods=3).mean()

    featured_df = featured_df.dropna().reset_index(drop=True)

    # Raw exogenous columns stay in the frame (forecast_future needs their history to
    # recurse forward) but never enter the model's own feature list - only their
    # shifted exo_*_lag1/roll7 versions do. Every raw column from either source file
    # is excluded, not just the ones listed in exo_cols: an unrenamed same-day column
    # ("Handover Success Rate ( 4G Intra System)") previously slipped through that
    # way as an unshifted, lookahead-leaking feature.
    raw_source_cols = (set(macro_df.columns) | set(carrier_daily.columns)) - {"date"}
    feature_cols = [c for c in get_feature_columns(featured_df) if c not in raw_source_cols]

    n = len(featured_df)
    n_train = int(n * train_ratio)
    n_val = int(n * val_ratio)

    train_data = featured_df.iloc[:n_train].copy().reset_index(drop=True)
    val_data = featured_df.iloc[n_train : n_train + n_val].copy().reset_index(drop=True)
    test_data = featured_df.iloc[n_train + n_val :].copy().reset_index(drop=True)

    # Fit scaler ONLY on train data per ML best practices
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
        "exo_cols": exo_cols,
    }

    print(f"[Multivariate] Datasets created with {len(feature_cols)} features (including {len(exo_cols)} exogenous network KPIs).")
    print(f"[Multivariate] Samples: Train={len(train_data)}, Val={len(val_data)}, Test={len(test_data)}")

    return datasets, scaler, feature_cols


if __name__ == "__main__":
    prepare_datasets()
