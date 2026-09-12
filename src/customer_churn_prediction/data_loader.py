import os
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Tuple, Dict, Any
from customer_churn_prediction.config import DEFAULT_DATASET_PATH, DROP_COLS, TARGET_COL

def load_and_clean_data(file_path: Path = DEFAULT_DATASET_PATH) -> Tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """
    Loads Telco Customer Churn dataset, cleans invalid characters,
    handles missing values, and isolates features, targets, and metadata.

    Returns:
        X: Feature dataframe
        y: Binary target series (1 for Churn, 0 for Stay)
        metadata: Metadata dataframe (CustomerID, CLTV, Churn Reason, etc.)
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Dataset not found at path: {file_path}")

    if str(file_path).endswith(".xlsx"):
        df = pd.read_excel(file_path)
    else:
        df = pd.read_csv(file_path)

    # Clean 'Total Charges' where tenure == 0 had whitespace string ' '
    if "Total Charges" in df.columns:
        df["Total Charges"] = pd.to_numeric(
            df["Total Charges"].astype(str).str.strip().replace("", "0"),
            errors="coerce"
        ).fillna(0.0)

    # Metadata dataframe retained for business recommendations and tracking
    meta_cols = [col for col in ["CustomerID", "CLTV", "Monthly Charges", "Contract", "Internet Service", "Churn Reason", "Tenure Months"] if col in df.columns]
    metadata = df[meta_cols].copy()

    # Target
    if TARGET_COL not in df.columns:
        if "Churn Label" in df.columns:
            y = (df["Churn Label"].str.strip().str.lower() == "yes").astype(int)
        elif "Churn" in df.columns:
            y = (df["Churn"].astype(str).str.strip().str.lower().isin(["yes", "1", "true"])).astype(int)
        else:
            raise ValueError(f"Could not find target column in dataset.")
    else:
        y = df[TARGET_COL].astype(int)

    # Features
    cols_to_drop = [c for c in DROP_COLS if c in df.columns]
    if TARGET_COL in df.columns and TARGET_COL not in cols_to_drop:
        cols_to_drop.append(TARGET_COL)

    X = df.drop(columns=cols_to_drop, errors="ignore").copy()

    return X, y, metadata

if __name__ == "__main__":
    X, y, meta = load_and_clean_data()
    print(f"Loaded X shape: {X.shape}, y shape: {y.shape}, meta shape: {meta.shape}")
    print(f"Target distribution:\n{y.value_counts(normalize=True)}")
