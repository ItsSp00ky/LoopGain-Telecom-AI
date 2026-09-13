import os
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Tuple, Dict, Any
from customer_churn_prediction.config import DEFAULT_DATASET_PATH, DROP_COLS

def load_and_clean_data(file_path: Path = DEFAULT_DATASET_PATH) -> Tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """
    Loads Maven Telecom Customer Churn dataset, cleans domain missing values,
    isolates features, target (Stayed vs Churned), and preserves customer metadata.

    Returns:
        X: Feature dataframe
        y: Binary target series (1 for Churn, 0 for Stay)
        metadata: Metadata dataframe for customer retention recommendation
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Dataset not found at path: {file_path}")

    df = pd.read_csv(file_path)

    # Filter to customers with established status (Stayed or Churned)
    # 'Joined' represents 454 new onboardings without a complete billing cycle
    if "Customer Status" in df.columns:
        df = df[df["Customer Status"].isin(["Stayed", "Churned"])].reset_index(drop=True)
        y = (df["Customer Status"] == "Churned").astype(int)
    elif "Churn" in df.columns:
        y = df["Churn"].astype(int)
    else:
        raise ValueError("Could not find Customer Status or Churn column in dataset.")

    # Domain-aware null imputation
    if "Offer" in df.columns:
        df["Offer"] = df["Offer"].fillna("None")

    if "Multiple Lines" in df.columns:
        df["Multiple Lines"] = df["Multiple Lines"].fillna("No phone service")

    if "Avg Monthly Long Distance Charges" in df.columns:
        df["Avg Monthly Long Distance Charges"] = df["Avg Monthly Long Distance Charges"].fillna(0.0)

    internet_service_cols = [
        "Internet Type", "Online Security", "Online Backup", "Device Protection Plan",
        "Premium Tech Support", "Streaming TV", "Streaming Movies", "Streaming Music",
        "Unlimited Data"
    ]
    for col in internet_service_cols:
        if col in df.columns:
            df[col] = df[col].fillna("No internet service")

    if "Avg Monthly GB Download" in df.columns:
        df["Avg Monthly GB Download"] = df["Avg Monthly GB Download"].fillna(0.0)

    # Metadata columns retained for business rules & discount targeting
    meta_cols = [
        c for c in [
            "Customer ID", "Customer Status", "Monthly Charge", "Total Charges",
            "Total Revenue", "Tenure in Months", "Offer", "Contract", "Internet Type",
            "Avg Monthly GB Download", "Total Extra Data Charges", "Total Refunds",
            "Churn Category", "Churn Reason", "Number of Referrals"
        ] if c in df.columns
    ]
    metadata = df[meta_cols].copy()

    # Feature isolation
    cols_to_drop = [c for c in DROP_COLS if c in df.columns]
    X = df.drop(columns=cols_to_drop, errors="ignore").copy()

    return X, y, metadata

if __name__ == "__main__":
    X, y, meta = load_and_clean_data()
    print(f"Loaded X shape: {X.shape}, y shape: {y.shape}, meta shape: {meta.shape}")
    print(f"Target distribution:\n{y.value_counts(normalize=True)}")
