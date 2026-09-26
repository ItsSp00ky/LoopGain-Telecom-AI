"""split.py: Chronological time-series data splitting without lookahead leakage.
"""

from pathlib import Path
import pandas as pd


def chronological_split(
    df: pd.DataFrame,
    train_ratio: float = 0.70,
    val_ratio: float = 0.15,
    save_dir: str | Path | None = "data",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Splits time series data strictly chronologically into Train, Validation, and Test sets.

    Ensures zero future lookahead leakage into earlier partitions.
    """
    df = df.sort_values("date").reset_index(drop=True)
    n = len(df)

    n_train = int(n * train_ratio)
    n_val = int(n * val_ratio)
    n_test = n - n_train - n_val

    train_df = df.iloc[:n_train].copy().reset_index(drop=True)
    val_df = df.iloc[n_train : n_train + n_val].copy().reset_index(drop=True)
    test_df = df.iloc[n_train + n_val :].copy().reset_index(drop=True)

    print("=" * 60)
    print("STEP 2: CHRONOLOGICAL TIME-SERIES DATA SPLIT")
    print("=" * 60)
    print(f"Total dataset size: {n} days")
    print(
        f"Train split: {len(train_df)} days ({len(train_df)/n:.1%}) | "
        f"{train_df['date'].min().strftime('%Y-%m-%d')} to {train_df['date'].max().strftime('%Y-%m-%d')}"
    )
    print(
        f"Val split:   {len(val_df)} days ({len(val_df)/n:.1%}) | "
        f"{val_df['date'].min().strftime('%Y-%m-%d')} to {val_df['date'].max().strftime('%Y-%m-%d')}"
    )
    print(
        f"Test split:  {len(test_df)} days ({len(test_df)/n:.1%}) | "
        f"{test_df['date'].min().strftime('%Y-%m-%d')} to {test_df['date'].max().strftime('%Y-%m-%d')}"
    )

    # Verification: assert strictly monotonic dates
    assert train_df["date"].max() < val_df["date"].min(), "Leakage detected between Train and Val!"
    assert val_df["date"].max() < test_df["date"].min(), "Leakage detected between Val and Test!"
    print("Validation check passed: No temporal overlap or future leakage.")

    if save_dir:
        save_path = Path(save_dir)
        save_path.mkdir(parents=True, exist_ok=True)
        train_df.to_csv(save_path / "train.csv", index=False)
        val_df.to_csv(save_path / "val.csv", index=False)
        test_df.to_csv(save_path / "test.csv", index=False)
        print(f"Saved partitions to {save_path.resolve()}: train.csv, val.csv, test.csv")

    print("Splitting step complete.\n")
    return train_df, val_df, test_df


def run_split_pipeline(input_csv: str = "data/traffic_kpi_clean.csv") -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Reads cleaned KPI data and executes chronological split."""
    df = pd.read_csv(input_csv)
    df["date"] = pd.to_datetime(df["date"])
    return chronological_split(df)


if __name__ == "__main__":
    run_split_pipeline()
