import os
import joblib
import json
import numpy as np
import pandas as pd
from typing import Dict, Any, Tuple
from pathlib import Path

from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.metrics import (
    roc_auc_score, average_precision_score, accuracy_score,
    precision_score, recall_score, f1_score, brier_score_loss,
    classification_report, confusion_matrix
)
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
import lightgbm as lgb
import xgboost as xgb

from customer_churn_prediction.config import (
    MODEL_DIR, REPORTS_DIR, DEFAULT_DATASET_PATH
)
from customer_churn_prediction.data_loader import load_and_clean_data
from customer_churn_prediction.feature_engineering import TelecomFeatureEngineer

def detect_cuda() -> bool:
    """
    Detects if NVIDIA CUDA acceleration is available for XGBoost.
    """
    try:
        clf = xgb.XGBClassifier(tree_method="hist", device="cuda", n_estimators=5)
        clf.fit(np.zeros((10, 2)), np.array([0, 1] * 5))
        return True
    except Exception:
        return False

def build_preprocessor(sample_transformed_df: pd.DataFrame) -> ColumnTransformer:
    """
    Constructs a ColumnTransformer that handles one-hot encoding for categoricals
    and standard scaling for numerical features.
    """
    num_cols = sample_transformed_df.select_dtypes(include=["int64", "float64"]).columns.tolist()
    cat_cols = sample_transformed_df.select_dtypes(include=["object", "string", "category"]).columns.tolist()

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), num_cols),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), cat_cols)
        ],
        remainder="drop"
    )
    return preprocessor

def get_candidate_models(use_cuda: bool = True) -> Dict[str, Any]:
    """
    Returns candidate classifiers with tuned hyperparameters.
    If use_cuda is True and CUDA is detected, XGBoost runs on NVIDIA GPU.
    """
    cuda_active = use_cuda and detect_cuda()
    xgb_params = {
        "n_estimators": 250,
        "learning_rate": 0.03,
        "max_depth": 5,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "scale_pos_weight": 2.0,
        "eval_metric": "logloss",
        "random_state": 42
    }

    if cuda_active:
        print("[GPU Acceleration] NVIDIA CUDA detected! Training XGBoost on GPU (device='cuda', tree_method='hist').")
        xgb_params["tree_method"] = "hist"
        xgb_params["device"] = "cuda"
    else:
        print("[Compute Engine] Running models on CPU.")
        xgb_params["n_jobs"] = -1

    return {
        "Logistic Regression": LogisticRegression(
            max_iter=1500,
            C=0.1,
            class_weight="balanced",
            random_state=42
        ),
        "Random Forest": RandomForestClassifier(
            n_estimators=300,
            max_depth=8,
            min_samples_split=10,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1
        ),
        "LightGBM": lgb.LGBMClassifier(
            n_estimators=200,
            learning_rate=0.03,
            max_depth=5,
            num_leaves=31,
            subsample=0.8,
            colsample_bytree=0.8,
            scale_pos_weight=2.0,
            random_state=42,
            verbose=-1
        ),
        "XGBoost": xgb.XGBClassifier(**xgb_params)
    }

def train_and_benchmark(
    data_path: Path = DEFAULT_DATASET_PATH,
    test_size: float = 0.20,
    random_state: int = 42,
    use_cuda: bool = True
) -> Dict[str, Any]:
    """
    Executes full data loading, feature engineering, 5-fold cross-validation,
    test evaluation, and selects the champion model.
    """
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading and cleaning dataset...")
    X_raw, y, metadata = load_and_clean_data(data_path)

    print("Splitting train and test sets (stratified)...")
    X_train_raw, X_test_raw, y_train, y_test, meta_train, meta_test = train_test_split(
        X_raw, y, metadata, test_size=test_size, random_state=random_state, stratify=y
    )

    # Feature engineering
    fe = TelecomFeatureEngineer()
    X_train_fe = fe.fit_transform(X_train_raw)
    X_test_fe = fe.transform(X_test_raw)

    preprocessor = build_preprocessor(X_train_fe)

    models = get_candidate_models(use_cuda=use_cuda)
    results = {}
    fitted_pipelines = {}

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=random_state)

    print("\nBenchmarking candidate models across 5-Fold Cross-Validation...")
    for name, clf in models.items():
        pipe = Pipeline(steps=[
            ("preprocessor", preprocessor),
            ("classifier", clf)
        ])

        # 5-fold CV on train set
        cv_scores = cross_val_score(pipe, X_train_fe, y_train, cv=cv, scoring="roc_auc", n_jobs=1 if "cuda" in str(getattr(clf, "device", "")) else -1)
        mean_cv_auc = float(np.mean(cv_scores))
        std_cv_auc = float(np.std(cv_scores))

        # Fit on entire train set
        pipe.fit(X_train_fe, y_train)
        fitted_pipelines[name] = pipe

        # Evaluate on test set
        y_probs = pipe.predict_proba(X_test_fe)[:, 1]
        y_preds = (y_probs >= 0.50).astype(int)

        test_roc_auc = float(roc_auc_score(y_test, y_probs))
        test_pr_auc = float(average_precision_score(y_test, y_probs))
        test_acc = float(accuracy_score(y_test, y_preds))
        test_prec = float(precision_score(y_test, y_preds, zero_division=0))
        test_rec = float(recall_score(y_test, y_preds, zero_division=0))
        test_f1 = float(f1_score(y_test, y_preds, zero_division=0))
        test_brier = float(brier_score_loss(y_test, y_probs))

        results[name] = {
            "cv_roc_auc_mean": round(mean_cv_auc, 4),
            "cv_roc_auc_std": round(std_cv_auc, 4),
            "test_roc_auc": round(test_roc_auc, 4),
            "test_pr_auc": round(test_pr_auc, 4),
            "test_accuracy": round(test_acc, 4),
            "test_precision": round(test_prec, 4),
            "test_recall": round(test_rec, 4),
            "test_f1": round(test_f1, 4),
            "test_brier_score": round(test_brier, 4)
        }
        print(f" -> {name:20s} | CV ROC-AUC: {mean_cv_auc:.4f} (±{std_cv_auc:.4f}) | Test ROC-AUC: {test_roc_auc:.4f} | PR-AUC: {test_pr_auc:.4f} | Recall: {test_rec:.4f}")

    # Determine champion model by test ROC-AUC
    champion_name = max(results, key=lambda k: results[k]["test_roc_auc"])
    champion_pipeline = fitted_pipelines[champion_name]

    print(f"\nChampion Model Selected: {champion_name} (ROC-AUC: {results[champion_name]['test_roc_auc']:.4f})")

    # Set inference device to cpu on champion classifier to avoid host-device memory mismatch warnings during inference
    champion_clf = champion_pipeline.named_steps["classifier"]
    if hasattr(champion_clf, "set_params"):
        try:
            champion_clf.set_params(device="cpu")
        except Exception:
            pass

    # Save full end-to-end inference pipeline: TelecomFeatureEngineer + Preprocessor + Champion Classifier
    full_inference_pipeline = Pipeline(steps=[
        ("feature_engineer", fe),
        ("preprocessor", champion_pipeline.named_steps["preprocessor"]),
        ("classifier", champion_clf)
    ])

    model_save_path = MODEL_DIR / "best_churn_model.joblib"
    joblib.dump(full_inference_pipeline, model_save_path)
    print(f"Saved champion pipeline to: {model_save_path}")

    # Save benchmark metrics to JSON
    benchmark_save_path = REPORTS_DIR / "model_benchmark.json"
    with open(benchmark_save_path, "w") as f:
        json.dump({
            "champion": champion_name,
            "cuda_enabled": use_cuda and detect_cuda(),
            "metrics": results
        }, f, indent=2)

    # Save test set evaluation data for visualization scripts
    test_eval_df = X_test_raw.copy()
    test_eval_df["y_true"] = y_test.values
    test_eval_df["churn_prob"] = full_inference_pipeline.predict_proba(X_test_raw)[:, 1]
    for c in meta_test.columns:
        if c not in test_eval_df.columns:
            test_eval_df[c] = meta_test[c].values
    test_eval_df.to_csv(REPORTS_DIR / "test_predictions.csv", index=False)

    return {
        "champion_name": champion_name,
        "results": results,
        "model_path": str(model_save_path)
    }

if __name__ == "__main__":
    train_and_benchmark()
