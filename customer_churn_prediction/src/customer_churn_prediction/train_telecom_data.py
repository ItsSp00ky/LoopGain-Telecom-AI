import time
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.metrics import roc_auc_score, average_precision_score, classification_report, confusion_matrix
import xgboost as xgb
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

def load_telecom_data(data_dir: Path = Path("churn_datasets/Telecom_data")):
    client_path = data_dir / "Client.csv"
    record_path = data_dir / "Record.csv"

    if not client_path.exists() or not record_path.exists():
        raise FileNotFoundError(f"Telecom_data files not found in {data_dir}")

    print("Loading Client.csv (100,000 records)...")
    df_client = pd.read_csv(client_path)
    print("Loading Record.csv (100,000 records)...")
    df_record = pd.read_csv(record_path)

    print("Merging on Customer_ID...")
    df = pd.merge(df_client, df_record, on="Customer_ID")
    return df

def train_telecom_gpu():
    console.print(Panel.fit("[bold green]Training XGBoost on New Telecom_data (100,000 Rows, 100 Features)[/bold green]"))

    df = load_telecom_data()
    y = df["churn"]
    X = df.drop(columns=["churn", "Customer_ID"])

    # Cast categoricals for XGBoost native support
    cat_cols = X.select_dtypes(include=["object", "string"]).columns.tolist()
    for c in cat_cols:
        X[c] = X[c].astype("category")

    print(f"Dataset shape: {X.shape[0]:,} rows, {X.shape[1]} features")
    print(f"Target distribution: {y.value_counts(normalize=True).to_dict()}")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    print("\nTraining XGBoost with CUDA GPU acceleration...")
    start = time.time()
    clf = xgb.XGBClassifier(
        n_estimators=400,
        learning_rate=0.03,
        max_depth=6,
        subsample=0.8,
        colsample_bytree=0.8,
        enable_categorical=True,
        tree_method="hist",
        device="cuda",
        eval_metric="logloss",
        random_state=42
    )
    clf.fit(X_train, y_train)
    train_time = time.time() - start

    # Switch device to cpu for fast inference without warning
    clf.set_params(device="cpu")

    probs = clf.predict_proba(X_test)[:, 1]
    preds = (probs >= 0.50).astype(int)

    roc_auc = float(roc_auc_score(y_test, probs))
    pr_auc = float(average_precision_score(y_test, probs))
    report = classification_report(y_test, preds, output_dict=True)

    table = Table(title="Telecom_data (100k) Evaluation Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Training Time (CUDA GPU)", f"{train_time:.2f} seconds")
    table.add_row("Test ROC-AUC", f"{roc_auc:.4f}")
    table.add_row("Test PR-AUC", f"{pr_auc:.4f}")
    table.add_row("Accuracy", f"{report['accuracy']:.4f}")
    table.add_row("Precision (Churn)", f"{report['1']['precision']:.4f}")
    table.add_row("Recall (Churn)", f"{report['1']['recall']:.4f}")
    table.add_row("F1-Score (Churn)", f"{report['1']['f1-score']:.4f}")
    console.print(table)

    # Top Features
    fi = pd.DataFrame({
        "feature": X.columns,
        "importance": clf.feature_importances_
    }).sort_values("importance", ascending=False).head(10)

    fi_table = Table(title="Top 10 Churn Drivers in Telecom_data")
    fi_table.add_column("Feature", style="yellow")
    fi_table.add_column("Relative Importance", style="magenta")
    for _, row in fi.iterrows():
        fi_table.add_row(row["feature"], f"{row['importance']:.4f}")
    console.print(fi_table)

    return {
        "roc_auc": roc_auc,
        "pr_auc": pr_auc,
        "train_time": train_time,
        "report": report
    }

if __name__ == "__main__":
    train_telecom_gpu()
