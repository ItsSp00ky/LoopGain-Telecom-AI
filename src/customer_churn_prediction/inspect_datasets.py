import os
import pandas as pd
import numpy as np

datasets = {
    "IBM_Telco": "churn_datasets/Telco_customer_churn.xlsx/Telco_customer_churn.xlsx",
    "Cell2Cell_Train": "churn_datasets/cell2celltrain.csv/cell2celltrain.csv",
    "Cell2Cell_Holdout": "churn_datasets/cell2celltrain.csv/cell2cellholdout.csv",
    "Generic_Training": "churn_datasets/customer_churn_dataset-testing-master.csv/customer_churn_dataset-training-master.csv",
    "Generic_Testing": "churn_datasets/customer_churn_dataset-testing-master.csv/customer_churn_dataset-testing-master.csv",
}

for name, path in datasets.items():
    print("=" * 70)
    print(f"Dataset: {name}")
    print(f"Path: {path}")
    if not os.path.exists(path):
        print("File NOT found!")
        continue

    if path.endswith(".xlsx"):
        df = pd.read_excel(path)
    else:
        df = pd.read_csv(path)

    print(f"Shape: {df.shape[0]} rows, {df.shape[1]} columns")
    print("\nColumns and Dtypes:")
    for col, dtype in zip(df.columns, df.dtypes):
        null_count = df[col].isnull().sum()
        sample_vals = df[col].dropna().unique()[:3].tolist()
        print(f" - {col} ({dtype}) | Missing: {null_count} ({null_count/len(df):.1%}) | Sample: {sample_vals}")

    # Check potential target columns
    potential_targets = [c for c in df.columns if any(k in c.lower() for k in ["churn", "target", "status", "leave"])]
    print("\nPotential Target Columns:", potential_targets)
    for pt in potential_targets:
        print(f"Value counts for {pt}:")
        print(df[pt].value_counts(dropna=False, normalize=True))
    print("\n")
