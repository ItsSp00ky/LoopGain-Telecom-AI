"""
=====================================================================
 forecast_and_save_models.py
 Purpose : Forecast 4G/LTE KPIs using XGBoost, evaluate performance,
           AND permanently save the trained models ("AI Brain") to disk.

 KPIs Predicted & Saved:
   1. E-RAB Drop Rate         (QoS / customer experience)
   2. 4G Cell Av. (%)         (network availability)
   3. Avg RRC Connected users (traffic demand / capacity planning)

 Output Files:
   - forecast_results/saved_models/model_<KPI>.json  (Trained XGBoost models)
   - forecast_results/saved_models/model_metadata.json (Feature list, dates, metrics)
   - forecast_results/model_metrics.csv               (Evaluation metrics)
   - forecast_results/feature_importances.json       (Importance weights)
   - forecast_results/predictions_<KPI>.csv          (Predictions vs Actual)

 Usage:
   python forecast_and_save_models.py
=====================================================================
"""

import pandas as pd
import numpy as np
import warnings
import json
import os
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

warnings.filterwarnings("ignore")

# ----------------------------- CONFIG ------------------------------ #
INPUT_FILE = "Data2_Cleaned.csv"
RESULTS_DIR = "forecast_results"
MODELS_DIR = os.path.join(RESULTS_DIR, "saved_models")

# KPIs to forecast (Tier 1 from strategy)
TARGET_KPIS = [
    "E-RAB Drop Rate",
    "4G Cell Av. (%)",
    "Avg RRC Connected users",
]

# Train/test split ratio
TRAIN_RATIO = 0.70

# Lag and rolling window sizes
LAG_DAYS = [1, 3, 7, 14]
ROLLING_WINDOWS = [7, 14]


# ------------------------------------------------------------------- #
# STEP 1 — FEATURE ENGINEERING (Lag + Rolling Stats)
# ------------------------------------------------------------------- #
def create_time_features(df: pd.DataFrame, target_col: str) -> pd.DataFrame:
    """
    Create lag features and rolling statistics for a target KPI.
    All features are computed WITHIN each earfcndl band to avoid
    data leakage across frequency bands.
    """
    df = df.copy()

    # --- Lag features ---
    for lag in LAG_DAYS:
        df[f"{target_col}_lag_{lag}"] = (
            df.groupby("earfcndl")[target_col].shift(lag)
        )

    # --- Rolling mean ---
    for window in ROLLING_WINDOWS:
        df[f"{target_col}_rolling_mean_{window}"] = (
            df.groupby("earfcndl")[target_col]
            .transform(lambda s: s.shift(1).rolling(window, min_periods=1).mean())
        )

    # --- Rolling std (volatility) ---
    for window in ROLLING_WINDOWS:
        df[f"{target_col}_rolling_std_{window}"] = (
            df.groupby("earfcndl")[target_col]
            .transform(lambda s: s.shift(1).rolling(window, min_periods=1).std())
        )

    # --- Rate of change ---
    df[f"{target_col}_diff_1"] = df.groupby("earfcndl")[target_col].diff(1)
    df[f"{target_col}_diff_7"] = df.groupby("earfcndl")[target_col].diff(7)

    return df


# ------------------------------------------------------------------- #
# STEP 2 — PREPARE FEATURES & TARGET
# ------------------------------------------------------------------- #
def prepare_model_data(df: pd.DataFrame, target_col: str):
    """
    Build the feature matrix X and target vector y.
    Drop rows with NaN from lag creation (first few days per band).
    """
    df = create_time_features(df, target_col)

    other_kpis = [k for k in TARGET_KPIS if k != target_col]
    drop_cols = ["Date"] + other_kpis
    drop_cols = [c for c in drop_cols if c in df.columns]

    X = df.drop(columns=drop_cols + [target_col])
    y = df[target_col]

    valid_mask = X.notna().all(axis=1) & y.notna()
    X = X[valid_mask]
    y = y[valid_mask]
    dates = df.loc[valid_mask, "Date"]

    return X, y, dates


# ------------------------------------------------------------------- #
# STEP 3 — TRAIN/TEST SPLIT (Chronological)
# ------------------------------------------------------------------- #
def chronological_split(X, y, dates, train_ratio=0.70):
    """Split data chronologically — 70% train, 30% test."""
    unique_dates = sorted(dates.unique())
    split_idx = int(len(unique_dates) * train_ratio)
    split_date = unique_dates[split_idx]

    train_mask = dates < split_date
    test_mask = dates >= split_date

    X_train, X_test = X[train_mask], X[test_mask]
    y_train, y_test = y[train_mask], y[test_mask]
    dates_train, dates_test = dates[train_mask], dates[test_mask]

    return X_train, X_test, y_train, y_test, dates_train, dates_test, split_date


# ------------------------------------------------------------------- #
# STEP 4 — TRAIN XGBoost MODEL
# ------------------------------------------------------------------- #
def train_xgboost(X_train, y_train, X_test, y_test):
    """Train an XGBoost regressor with tuned hyperparameters."""
    try:
        from xgboost import XGBRegressor
    except ImportError:
        raise ImportError("xgboost not installed. Run: pip install xgboost")

    model = XGBRegressor(
        n_estimators=500,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=3,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        early_stopping_rounds=30,
        verbosity=0,
    )

    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )

    return model


# ------------------------------------------------------------------- #
# STEP 5 — EVALUATE
# ------------------------------------------------------------------- #
def evaluate_model(y_true, y_pred, kpi_name):
    """Calculate and return evaluation metrics."""
    mae = mean_absolute_error(y_true, y_pred)
    rmse = np.sqrt(mean_squared_error(y_true, y_pred))
    r2 = r2_score(y_true, y_pred)

    mask = y_true != 0
    if mask.sum() > 0:
        mape = np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100
    else:
        mape = float("nan")

    return {
        "KPI": kpi_name,
        "MAE": round(mae, 4),
        "RMSE": round(rmse, 4),
        "MAPE (%)": round(mape, 2),
        "R2": round(r2, 4),
    }


# ------------------------------------------------------------------- #
# STEP 6 — FEATURE IMPORTANCE
# ------------------------------------------------------------------- #
def get_feature_importance(model, feature_names, top_n=10):
    """Get top N most important features."""
    importance = model.feature_importances_
    feat_imp = sorted(
        zip(feature_names, importance),
        key=lambda x: x[1],
        reverse=True,
    )
    return feat_imp[:top_n]


# ------------------------------------------------------------------- #
# STEP 7 — SAVE & RELOAD MODEL HELPERS
# ------------------------------------------------------------------- #
def sanitize_kpi_name(kpi_name: str) -> str:
    """Sanitize KPI string for file naming."""
    return kpi_name.replace(" ", "_").replace("(%)", "pct").replace(".", "")


def save_trained_model(model, kpi_name: str, feature_columns: list, metrics: dict, models_dir: str):
    """
    Saves the trained XGBoost model binary (JSON format) and its feature schema.
    This saves the actual learned parameters/trees.
    """
    os.makedirs(models_dir, exist_ok=True)
    clean_name = sanitize_kpi_name(kpi_name)
    
    # 1. Save model weights/architecture
    model_filename = f"model_{clean_name}.json"
    model_path = os.path.join(models_dir, model_filename)
    model.save_model(model_path)

    # 2. Save feature columns schema
    schema_filename = f"features_{clean_name}.json"
    schema_path = os.path.join(models_dir, schema_filename)
    with open(schema_path, "w") as f:
        json.dump(feature_columns, f, indent=2)

    return model_path, schema_path


def load_saved_model(kpi_name: str, models_dir: str = MODELS_DIR):
    """
    Helper function to load a previously trained model and its feature schema.
    Usage example:
        model, features = load_saved_model('E-RAB Drop Rate')
        predictions = model.predict(new_data[features])
    """
    from xgboost import XGBRegressor
    clean_name = sanitize_kpi_name(kpi_name)
    
    model_path = os.path.join(models_dir, f"model_{clean_name}.json")
    schema_path = os.path.join(models_dir, f"features_{clean_name}.json")

    if not os.path.exists(model_path):
        raise FileNotFoundError(f"No saved model found at {model_path}")

    model = XGBRegressor()
    model.load_model(model_path)

    with open(schema_path, "r") as f:
        features = json.load(f)

    return model, features


# ------------------------------------------------------------------- #
# MAIN PIPELINE
# ------------------------------------------------------------------- #
def main():
    print("=" * 65)
    print("  4G/LTE KPI FORECASTING & MODEL SAVING PIPELINE")
    print("=" * 65)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    os.makedirs(MODELS_DIR, exist_ok=True)

    print(f"\n[1] Loading '{INPUT_FILE}' ...")
    df = pd.read_csv(INPUT_FILE, parse_dates=["Date"])
    print(f"    Shape: {df.shape}")
    print(f"    Date range: {df['Date'].min().date()} -> {df['Date'].max().date()}")

    all_metrics = []
    all_importances = {}
    all_predictions = {}
    saved_model_paths = {}

    for i, kpi in enumerate(TARGET_KPIS, 1):
        print(f"\n{'='*65}")
        print(f"  [{i}/{len(TARGET_KPIS)}] Processing KPI: {kpi}")
        print(f"{'='*65}")

        # Features
        print("  [a] Creating lag + rolling features ...")
        X, y, dates = prepare_model_data(df, kpi)
        feature_names = X.columns.tolist()

        # Split
        print("  [b] Chronological split (70% train / 30% test) ...")
        X_train, X_test, y_train, y_test, dates_train, dates_test, split_date = \
            chronological_split(X, y, dates, TRAIN_RATIO)

        # Train
        print(f"  [c] Training XGBoost on {X_train.shape[0]} samples ...")
        model = train_xgboost(X_train, y_train, X_test, y_test)

        # Predict & Evaluate
        y_pred = model.predict(X_test)
        metrics = evaluate_model(y_test.values, y_pred, kpi)
        all_metrics.append(metrics)
        print(f"  [d] Results -> R2: {metrics['R2']} | MAPE: {metrics['MAPE (%)']}% | MAE: {metrics['MAE']}")

        # Feature Importance
        feat_imp = get_feature_importance(model, feature_names)
        all_importances[kpi] = feat_imp

        # Save Predictions CSV
        clean_name = sanitize_kpi_name(kpi)
        pred_df = pd.DataFrame({
            "Date": dates_test.values,
            "earfcndl": df.loc[dates_test.index, "earfcndl"].values,
            "Actual": y_test.values,
            "Predicted": np.round(y_pred, 4),
        })
        pred_file = os.path.join(RESULTS_DIR, f"predictions_{clean_name}.csv")
        pred_df.to_csv(pred_file, index=False)
        all_predictions[kpi] = pred_df

        # --- SAVE THE MODEL ("AI BRAIN") TO DISK ---
        m_path, s_path = save_trained_model(model, kpi, feature_names, metrics, MODELS_DIR)
        saved_model_paths[kpi] = {"model": m_path, "schema": s_path}
        print(f"  [e] AI Model Brain saved to: {m_path}")
        print(f"      Feature Schema saved to: {s_path}")

    # ---- Save Metadata & Summary ---- #
    print("\n" + "=" * 65)
    print("  FORECASTING COMPLETE & MODELS PERSISTED")
    print("=" * 65)

    # Metrics CSV
    metrics_df = pd.DataFrame(all_metrics)
    print("\n" + metrics_df.to_string(index=False))
    metrics_file = os.path.join(RESULTS_DIR, "model_metrics.csv")
    metrics_df.to_csv(metrics_file, index=False)

    # Feature Importances JSON
    with open(os.path.join(RESULTS_DIR, "feature_importances.json"), "w") as f:
        serializable = {k: [(n, round(float(v), 4)) for n, v in vals] for k, vals in all_importances.items()}
        json.dump(serializable, f, indent=2)

    # Overall Models Manifest
    manifest = {
        "description": "Trained XGBoost models and schemas for 4G/LTE forecasting",
        "train_date_range": f"{df['Date'].min().date()} to {split_date.date()}",
        "test_date_range": f"{split_date.date()} to {df['Date'].max().date()}",
        "kpis": TARGET_KPIS,
        "metrics": all_metrics,
        "models": saved_model_paths,
    }
    with open(os.path.join(MODELS_DIR, "model_metadata.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nAll models saved in: {MODELS_DIR}/")
    print(f"Metadata manifest saved in: {os.path.join(MODELS_DIR, 'model_metadata.json')}")

    # Verification Test: reload one saved model and run test inference
    print("\n[Verification] Reloading saved model from disk to test inference...")
    test_kpi = "Avg RRC Connected users"
    loaded_model, loaded_feats = load_saved_model(test_kpi)
    sample_test = X_test.iloc[:1][loaded_feats]
    test_pred = loaded_model.predict(sample_test)
    print(f"  Successfully loaded '{test_kpi}' model from disk!")
    print(f"  Sample inference on test record: {test_pred[0]:.4f}")
    print("=" * 65)

    return metrics_df, all_importances, all_predictions


if __name__ == "__main__":
    main()
