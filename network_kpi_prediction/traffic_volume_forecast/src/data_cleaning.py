"""clean.py: Data cleaning, formatting, validation, and anomaly treatment for KPI time-series data."""

from pathlib import Path
import pandas as pd
import numpy as np

_PKG_ROOT = Path(__file__).resolve().parent.parent


def resolve_raw_traffic_file(file_path: Path | str | None = None) -> Path:
    """Dynamically resolves the raw 4G traffic data file from standard repository locations."""
    if file_path:
        p = Path(file_path)
        if p.exists():
            return p
        if (_PKG_ROOT / file_path).exists():
            return _PKG_ROOT / file_path

    candidates = [
        _PKG_ROOT.parent / "data" / "all the data" / "DAILY NETWORK KPIs v2" / "Year.csv",
        _PKG_ROOT.parent / "data" / "raw" / "4g_traffic_volume_daily.csv",
        _PKG_ROOT / "data" / "raw" / "4g_traffic_volume_daily.csv",
        _PKG_ROOT / "data" / "4g_traffic_volume_daily.csv",
        _PKG_ROOT / "Year.csv",
        Path("Year.csv"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def load_raw_data(file_path: Path | str | None = None) -> pd.DataFrame:
    """Loads raw KPI data from CSV, cleaning up headers and string formatting."""
    resolved_path = resolve_raw_traffic_file(file_path)
    if not resolved_path.exists():
        raise FileNotFoundError(f"Input file not found: {resolved_path}")

    df = pd.read_csv(resolved_path)

    # Strip quotes and leading/trailing whitespace from column names
    df.columns = [c.strip().strip('"') for c in df.columns]

    # Identify date column and target column
    date_cols = [c for c in df.columns if "date" in c.lower()]
    if not date_cols:
        raise ValueError("No 'Date' column identified in raw data.")
    date_col = date_cols[0]

    preferred_val = [c for c in df.columns if c != date_col and any(k in c.lower() for k in ["volume", "gb", "kpi", "traffic"])]
    if preferred_val:
        val_col = preferred_val[0]
    else:
        val_cols = [c for c in df.columns if c != date_col]
        if not val_cols:
            raise ValueError("No KPI value column identified in raw data.")
        val_col = val_cols[0]

    # Standardize column names
    df = df.rename(columns={date_col: "date", val_col: "kpi_volume_gb"})

    # Parse and clean numerical target
    df["kpi_volume_gb"] = (
        df["kpi_volume_gb"]
        .astype(str)
        .str.replace(",", "", regex=False)
        .str.strip('"')
        .str.strip()
        .astype(float)
    )

    # Parse dates with robust fallback
    try:
        df["date"] = pd.to_datetime(df["date"], format="%m/%d/%y")
    except Exception:
        df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    return df


def validate_and_regularize(df: pd.DataFrame) -> pd.DataFrame:
    """Validates date continuity and regularizes daily frequency."""
    df = df.drop_duplicates(subset=["date"]).reset_index(drop=True)

    min_date = df["date"].min()
    max_date = df["date"].max()
    full_idx = pd.date_range(start=min_date, end=max_date, freq="D", name="date")

    df = df.set_index("date").reindex(full_idx)
    missing_count = df["kpi_volume_gb"].isna().sum()
    if missing_count > 0:
        print(f"[Warning] Imputing {missing_count} missing date rows via linear interpolation.")
        df["kpi_volume_gb"] = df["kpi_volume_gb"].interpolate(method="time")

    df = df.reset_index()
    return df


def detect_and_treat_anomalies(
    df: pd.DataFrame, z_threshold: float = 3.5
) -> pd.DataFrame:
    """Detects severe single-day transient reporting/outage anomalies using weekly-adjusted

    seasonal residuals, preserving authentic weekly peaks while fixing extreme outliers.
    """
    df = df.copy()
    df["kpi_volume_gb_raw"] = df["kpi_volume_gb"]

    # Calculate local trend via centered rolling mean
    trend = df["kpi_volume_gb"].rolling(window=15, center=True, min_periods=5).mean()
    trend = trend.bfill().ffill()

    # Day-of-week seasonal effect
    overall_mean = df["kpi_volume_gb"].mean()
    dow_effect = df.groupby(df["date"].dt.dayofweek)["kpi_volume_gb"].transform("mean") - overall_mean
    expected = trend + dow_effect
    residuals = df["kpi_volume_gb"] - expected

    # Robust standard deviation using IQR / 1.349
    iqr = residuals.quantile(0.75) - residuals.quantile(0.25)
    robust_std = iqr / 1.349 if iqr > 0 else residuals.std()
    z_scores = residuals / (robust_std + 1e-6)

    df["is_anomaly"] = z_scores.abs() > z_threshold

    num_anomalies = df["is_anomaly"].sum()
    if num_anomalies > 0:
        print(f"[Info] Detected {num_anomalies} true structural anomaly/outage days (|z| > {z_threshold}):")
        cleaned_series = df["kpi_volume_gb"].copy()
        for idx in df[df["is_anomaly"]].index:
            row = df.loc[idx]
            date_str = row["date"].strftime("%Y-%m-%d")
            raw_val = row["kpi_volume_gb_raw"]
            exp_val = expected.iloc[idx]
            z_val = z_scores.iloc[idx]
            print(f"  - {date_str}: Raw = {raw_val:,.2f} GB, Expected = {exp_val:,.2f} GB (z-score = {z_val:.2f})")

            # Interpolate anomaly value using same day of week from neighboring weeks
            t_minus_7 = idx - 7 if idx >= 7 else None
            t_plus_7 = idx + 7 if idx + 7 < len(df) else None
            candidates = []
            if t_minus_7 is not None and not df.iloc[t_minus_7]["is_anomaly"]:
                candidates.append(df.iloc[t_minus_7]["kpi_volume_gb_raw"])
            if t_plus_7 is not None and not df.iloc[t_plus_7]["is_anomaly"]:
                candidates.append(df.iloc[t_plus_7]["kpi_volume_gb_raw"])

            imputed_val = float(np.mean(candidates)) if candidates else float(exp_val)
            cleaned_series.iloc[idx] = imputed_val
            print(f"    -> Imputed {date_str} to: {imputed_val:,.2f} GB")

        df["kpi_volume_gb"] = cleaned_series
    else:
        print("[Info] No extreme anomalies detected.")

    return df


def run_clean_pipeline(
    raw_path: str | Path | None = None,
    out_paths: list[str | Path] | None = None,
    z_threshold: float = 3.0,
) -> pd.DataFrame:
    """Executes the full cleaning pipeline and writes cleaned CSV outputs."""
    resolved_raw = resolve_raw_traffic_file(raw_path)
    if out_paths is None:
        out_paths = [_PKG_ROOT / "data" / "traffic_kpi_clean.csv"]

    print("=" * 60)
    print("STEP 1: CLEANING AND VALIDATING KPI DATA")
    print("=" * 60)
    print(f"Reading raw data from: {resolved_raw.resolve()}")
    df = load_raw_data(resolved_raw)
    print(f"Raw rows loaded: {len(df)}")

    df = validate_and_regularize(df)
    print(f"Regularized date range: {df['date'].min().strftime('%Y-%m-%d')} to {df['date'].max().strftime('%Y-%m-%d')} (Total days: {len(df)})")

    df = detect_and_treat_anomalies(df, z_threshold=z_threshold)

    # Save to outputs
    for path_item in out_paths:
        p = Path(path_item)
        if not p.is_absolute():
            p = _PKG_ROOT / p
        p.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(p, index=False)
        print(f"Successfully saved clean dataset to: {p.resolve()}")

    print("Cleaning step complete.\n")
    return df


if __name__ == "__main__":
    run_clean_pipeline()
