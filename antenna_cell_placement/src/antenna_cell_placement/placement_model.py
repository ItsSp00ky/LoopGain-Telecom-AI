"""
AI Machine Learning Models for Cell Site Placement Suitability and Equipment Recommendation.
Uses LightGBM and XGBoost with Stratified K-Fold CV, ROC/PR evaluation, and feature importance analysis.
"""

import json
from pathlib import Path
from typing import Dict, Tuple, Any, List

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from lightgbm import LGBMClassifier
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
    auc,
    classification_report,
)
from sklearn.model_selection import StratifiedKFold
from xgboost import XGBClassifier

from antenna_cell_placement.config import (
    CLEANED_SITES_PARQUET,
    SUITABILITY_MODEL_PATH,
    EQUIPMENT_MODEL_PATH,
    MODEL_METRICS_PATH,
    REPORTS_DIR,
    MODELS_DIR,
    LIBYA_BBOX,
)
from antenna_cell_placement.feature_engineering import GeospatialFeatureExtractor


# Modeling Features used for Suitability Prediction
SUITABILITY_FEATURE_COLS = [
    "population_density_1km",
    "population_sum_3km",
    "population_sum_5km",
    "elevation_m",
    "elevation_prominence_3km",
    "terrain_slope_deg",
    "dist_to_nearest_road_m",
    "dist_to_nearest_settlement_m",
    "dist_to_nearest_site_m",
    "site_density_3km",
    "site_density_5km",
    "site_density_10km",
]


EQUIPMENT_FEATURE_COLS = [
    "population_density_1km",
    "population_sum_3km",
    "population_sum_5km",
    "elevation_m",
    "elevation_prominence_3km",
    "terrain_slope_deg",
    "dist_to_nearest_road_m",
    "dist_to_nearest_settlement_m",
    "dist_to_nearest_site_m",
    "site_density_3km",
    "site_density_5km",
]


def label_equipment_tiers(df: pd.DataFrame) -> pd.Series:
    """
    Rule-based equipment tier for each site (first matching rule wins). These rules
    are the training target of the equipment recommender, so the model is learning
    to reproduce them; several rule inputs are also model features.
    """
    pop_1km = df["population_density_1km"]
    micro = (df["primary_tower_type"] == "MICRO") | (
        (pop_1km > 2500) & (df["dist_to_nearest_site_m"] < 250)
    )
    urban = (pop_1km >= 1200) | (df["total_bandwidth_mhz"] >= 40.0) | (df["total_carrier_count"] >= 3)
    suburban = (pop_1km >= 150) | (df["total_bandwidth_mhz"] >= 20.0) | (df["dist_to_nearest_road_m"] < 500)
    tiers = np.select(
        [micro, urban, suburban],
        ["Micro_Cell_Hotspot", "Urban_HighCapacity_Macro", "Suburban_Standard_Macro"],
        default="Rural_Coverage_Macro",
    )
    return pd.Series(tiers, index=df.index)


def generate_synthetic_negative_samples(
    df_positives: pd.DataFrame,
    extractor: GeospatialFeatureExtractor,
    n_negatives: int = 3000,
    random_state: int = 42
) -> pd.DataFrame:
    """
    Generates realistic geospatial negative samples (non-site candidate locations)
    across Libya to train the placement suitability classifier.
    Combines:
    1. Populated settlement corridors currently lacking cell sites
    2. Highway & road corridors (> 5km from any tower)
    3. Intermediate buffer regions around Libyan cities
    4. Remote desert / rural background controls
    """
    np.random.seed(random_state)
    neg_lons = []
    neg_lats = []

    extractor.load_layers()

    # Subset 1: Highway corridors outside existing coverage (~35%)
    roads_gdf = extractor.road_tree
    # Sample along roads in Libya
    road_pts = extractor.road_tree.data
    road_sample_idxs = np.random.choice(len(road_pts), size=min(len(road_pts), n_negatives * 2), replace=False)
    # Convert UTM to WGS84
    import geopandas as gpd
    from shapely.geometry import Point
    sample_utm_pts = [Point(road_pts[idx, 0], road_pts[idx, 1]) for idx in road_sample_idxs]
    gdf_road_samples = gpd.GeoDataFrame(geometry=sample_utm_pts, crs="EPSG:32633").to_crs("EPSG:4326")

    from pyproj import Transformer
    from antenna_cell_placement.config import CRS_WGS84, CRS_PROJECTED_LIBYA
    transformer = Transformer.from_crs(CRS_WGS84, CRS_PROJECTED_LIBYA, always_xy=True)
    if extractor.site_tree_all is None:
        raise ValueError("Set the existing-site inventory before negative sampling")
    for pt in gdf_road_samples.geometry:
        if len(neg_lons) >= int(n_negatives * 0.40):
            break
        # Filter within Libya bounds
        if LIBYA_BBOX["min_lon"] <= pt.x <= LIBYA_BBOX["max_lon"] and LIBYA_BBOX["min_lat"] <= pt.y <= LIBYA_BBOX["max_lat"]:
            # Check distance to existing sites
            # Add small random jitter (50m to 500m)
            jitter_x = np.random.uniform(-0.005, 0.005)
            jitter_y = np.random.uniform(-0.005, 0.005)
            cand_lon, cand_lat = pt.x + jitter_x, pt.y + jitter_y
            if not (LIBYA_BBOX["min_lon"] <= cand_lon <= LIBYA_BBOX["max_lon"] and
                    LIBYA_BBOX["min_lat"] <= cand_lat <= LIBYA_BBOX["max_lat"]):
                continue
            candidate_xy = transformer.transform(cand_lon, cand_lat)
            distance, _ = extractor.site_tree_all.query(candidate_xy)
            if distance <= 5000.0:
                continue
            neg_lons.append(cand_lon)
            neg_lats.append(cand_lat)

    # Subset 2: Populated places perimeter (~30%)
    for geom in extractor.places_df.geometry:
        if len(neg_lons) >= int(n_negatives * 0.70):
            break
        # Convert place pt to WGS84
        pt_wgs = gpd.GeoDataFrame(geometry=[geom], crs="EPSG:32633").to_crs("EPSG:4326").geometry.iloc[0]
        # Generate candidates in 3km to 15km ring around towns
        angles = np.linspace(0, 2 * np.pi, 8, endpoint=False)
        radii = np.random.uniform(0.03, 0.12, len(angles))  # ~3km to 12km in degrees
        for r, theta in zip(radii, angles):
            cand_lon = pt_wgs.x + r * np.cos(theta)
            cand_lat = pt_wgs.y + r * np.sin(theta)
            if LIBYA_BBOX["min_lon"] <= cand_lon <= LIBYA_BBOX["max_lon"] and LIBYA_BBOX["min_lat"] <= cand_lat <= LIBYA_BBOX["max_lat"]:
                neg_lons.append(cand_lon)
                neg_lats.append(cand_lat)

    # Subset 3: General territorial background / rural controls (~30%)
    while len(neg_lons) < n_negatives:
        rand_lon = np.random.uniform(LIBYA_BBOX["min_lon"], LIBYA_BBOX["max_lon"])
        rand_lat = np.random.uniform(LIBYA_BBOX["min_lat"], LIBYA_BBOX["max_lat"])
        neg_lons.append(rand_lon)
        neg_lats.append(rand_lat)

    neg_lons = neg_lons[:n_negatives]
    neg_lats = neg_lats[:n_negatives]

    print(f"Extracting features for {len(neg_lons)} candidate non-site negative locations...")
    df_neg_features = extractor.extract_features(neg_lons, neg_lats, is_existing_site=False)
    df_neg_features["is_cell_site"] = 0

    return df_neg_features


def prepare_training_data(
    df_sites_enriched: pd.DataFrame,
    extractor: GeospatialFeatureExtractor,
    n_negatives: int = 3000
) -> Tuple[pd.DataFrame, pd.Series]:
    """Prepares balanced positive and negative samples for site placement modeling."""
    df_pos = df_sites_enriched.copy()
    df_pos["is_cell_site"] = 1

    df_neg = generate_synthetic_negative_samples(df_pos, extractor, n_negatives=n_negatives)

    # Select common features
    common_cols = SUITABILITY_FEATURE_COLS + ["is_cell_site", "canonical_latitude", "canonical_longitude"]
    df_all = pd.concat([df_pos[common_cols], df_neg[common_cols]], ignore_index=True)

    # Shuffle
    df_all = df_all.sample(frac=1.0, random_state=42).reset_index(drop=True)

    X = df_all[SUITABILITY_FEATURE_COLS]
    y = df_all["is_cell_site"]

    return X, y, df_all


def train_suitability_model(
    X: pd.DataFrame,
    y: pd.Series,
    output_dir: Path = MODELS_DIR,
    reports_dir: Path = REPORTS_DIR
) -> Dict[str, Any]:
    """
    Trains and cross-validates LightGBM and XGBoost models for Cell Placement Suitability.
    Saves champion pipeline artifact and evaluation charts.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    print("Training Cell Site Placement Suitability Model (5-Fold Stratified CV)...")
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    lgb_oof_preds = np.zeros(len(y))
    xgb_oof_preds = np.zeros(len(y))

    lgb_models = []
    xgb_models = []

    for fold, (train_idx, val_idx) in enumerate(skf.split(X, y), start=1):
        X_train, y_train = X.iloc[train_idx], y.iloc[train_idx]
        X_val, y_val = X.iloc[val_idx], y.iloc[val_idx]

        # LightGBM Classifier
        clf_lgb = LGBMClassifier(
            n_estimators=300,
            learning_rate=0.04,
            max_depth=6,
            num_leaves=31,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42 + fold,
            verbose=-1,
        )
        clf_lgb.fit(X_train, y_train)
        lgb_oof_preds[val_idx] = clf_lgb.predict_proba(X_val)[:, 1]
        lgb_models.append(clf_lgb)

        # XGBoost Classifier
        clf_xgb = XGBClassifier(
            n_estimators=300,
            learning_rate=0.04,
            max_depth=5,
            subsample=0.8,
            colsample_bytree=0.8,
            eval_metric="logloss",
            random_state=42 + fold,
        )
        clf_xgb.fit(X_train, y_train)
        xgb_oof_preds[val_idx] = clf_xgb.predict_proba(X_val)[:, 1]
        xgb_models.append(clf_xgb)

    # Evaluate LightGBM
    lgb_auc = roc_auc_score(y, lgb_oof_preds)
    lgb_precision, lgb_recall, _ = precision_recall_curve(y, lgb_oof_preds)
    lgb_pr_auc = auc(lgb_recall, lgb_precision)
    lgb_binary = (lgb_oof_preds >= 0.5).astype(int)
    lgb_acc = accuracy_score(y, lgb_binary)
    lgb_f1 = f1_score(y, lgb_binary)
    lgb_brier = brier_score_loss(y, lgb_oof_preds)

    # Evaluate XGBoost
    xgb_auc = roc_auc_score(y, xgb_oof_preds)
    xgb_precision, xgb_recall, _ = precision_recall_curve(y, xgb_oof_preds)
    xgb_pr_auc = auc(xgb_recall, xgb_precision)
    xgb_binary = (xgb_oof_preds >= 0.5).astype(int)
    xgb_acc = accuracy_score(y, xgb_binary)
    xgb_f1 = f1_score(y, xgb_binary)

    print("\n" + "="*50)
    print("MODEL EVALUATION BENCHMARK RESULTS")
    print("="*50)
    print(f"LightGBM -> ROC-AUC: {lgb_auc:.4f} | PR-AUC: {lgb_pr_auc:.4f} | Accuracy: {lgb_acc:.4f} | F1: {lgb_f1:.4f} | Brier: {lgb_brier:.4f}")
    print(f"XGBoost  -> ROC-AUC: {xgb_auc:.4f} | PR-AUC: {xgb_pr_auc:.4f} | Accuracy: {xgb_acc:.4f} | F1: {xgb_f1:.4f}")

    # Select Champion Model (LightGBM) and retrain on full dataset
    champion_model = LGBMClassifier(
        n_estimators=350,
        learning_rate=0.035,
        max_depth=6,
        num_leaves=31,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        verbose=-1,
    )
    champion_model.fit(X, y)
    model_path = output_dir / SUITABILITY_MODEL_PATH.name
    joblib.dump(champion_model, model_path)
    print(f"Saved Champion Placement Suitability Model to: {model_path}")

    # Generate Evaluation Visualizations
    # 1. ROC Curve
    fpr, tpr, _ = roc_curve(y, lgb_oof_preds)
    plt.figure(figsize=(7, 6))
    plt.plot(fpr, tpr, color="#2563eb", lw=2.5, label=f"LightGBM (AUC = {lgb_auc:.4f})")
    plt.plot([0, 1], [0, 1], color="#94a3b8", lw=1.5, linestyle="--")
    plt.xlim([0.0, 1.0])
    plt.ylim([0.0, 1.05])
    plt.xlabel("False Positive Rate", fontsize=12)
    plt.ylabel("True Positive Rate", fontsize=12)
    plt.title("Cell Site Placement Suitability - ROC Curve", fontsize=14, fontweight="bold")
    plt.legend(loc="lower right", fontsize=11)
    plt.grid(True, alpha=0.3)
    roc_img_path = reports_dir / "suitability_roc_curve.png"
    plt.savefig(roc_img_path, dpi=300, bbox_inches="tight")
    plt.close()

    # 2. Feature Importance
    importances = champion_model.feature_importances_
    df_imp = pd.DataFrame({
        "Feature": SUITABILITY_FEATURE_COLS,
        "Importance": importances
    }).sort_values("Importance", ascending=True)

    plt.figure(figsize=(8, 6))
    plt.barh(df_imp["Feature"], df_imp["Importance"], color="#3b82f6", edgecolor="#1d4ed8")
    plt.xlabel("Importance (Split Gain)", fontsize=12)
    plt.title("Key Geospatial Drivers for Cell Site Placement", fontsize=14, fontweight="bold")
    plt.grid(axis="x", alpha=0.3)
    imp_img_path = reports_dir / "suitability_feature_importance.png"
    plt.savefig(imp_img_path, dpi=300, bbox_inches="tight")
    plt.close()

    # 3. Confusion Matrix
    cm = confusion_matrix(y, lgb_binary)
    plt.figure(figsize=(6, 5))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues", cbar=False,
                xticklabels=["Non-Site", "Cell Site"], yticklabels=["Non-Site", "Cell Site"])
    plt.xlabel("Predicted", fontsize=12)
    plt.ylabel("Actual", fontsize=12)
    plt.title("Placement Suitability Confusion Matrix", fontsize=14, fontweight="bold")
    cm_img_path = reports_dir / "suitability_confusion_matrix.png"
    plt.savefig(cm_img_path, dpi=300, bbox_inches="tight")
    plt.close()

    metrics = {
        "model": "LightGBM Classifier",
        "roc_auc": round(float(lgb_auc), 4),
        "pr_auc": round(float(lgb_pr_auc), 4),
        "accuracy": round(float(lgb_acc), 4),
        "f1_score": round(float(lgb_f1), 4),
        "precision": round(float(precision_score(y, lgb_binary)), 4),
        "recall": round(float(recall_score(y, lgb_binary)), 4),
        "brier_score": round(float(lgb_brier), 4),
        "training_samples": len(X),
        "positive_sites": int(y.sum()),
        "negative_candidates": int((1 - y).sum()),
        "feature_count": len(SUITABILITY_FEATURE_COLS),
        "features": SUITABILITY_FEATURE_COLS,
    }

    metrics_path = reports_dir / MODEL_METRICS_PATH.name
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"Saved benchmark metrics to: {metrics_path}")
    return metrics


def train_equipment_recommender(
    df_sites_enriched: pd.DataFrame,
    output_dir: Path = MODELS_DIR
) -> Dict[str, Any]:
    """
    Trains a model to predict the optimal equipment tier and bandwidth capacity
    for a chosen cell site location based on population demand and terrain.
    Tiers:
    - Tier 1: Rural_Coverage_Macro (single carrier 800/900 or 1800, low bandwidth)
    - Tier 2: Suburban_Macro (standard 4G LTE, 20MHz bandwidth)
    - Tier 3: Urban_HighCapacity_Macro (multi-carrier LTE-A, >=40MHz bandwidth)
    - Tier 4: Micro_Cell_Offload (small cell / hotspot in high density)
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    df = df_sites_enriched.copy()
    df["equipment_tier"] = label_equipment_tiers(df)

    features = EQUIPMENT_FEATURE_COLS

    X = df[features]
    y = df["equipment_tier"]

    from sklearn.ensemble import RandomForestClassifier
    clf_eq = RandomForestClassifier(n_estimators=200, max_depth=8, random_state=42)
    clf_eq.fit(X, y)

    model_path = output_dir / EQUIPMENT_MODEL_PATH.name
    joblib.dump(clf_eq, model_path)
    print(f"Saved Equipment Recommendation Model to: {model_path}")

    # Accuracy
    acc = accuracy_score(y, clf_eq.predict(X))
    print(
        f"Equipment Recommendation In-Sample Accuracy: {acc:.4f} "
        "(scored on its own training data; run `evaluate` for held-out numbers)"
    )

    return {
        "equipment_model_path": str(model_path),
        "accuracy": round(float(acc), 4),
        "classes": sorted(list(clf_eq.classes_)),
    }


def train_all_models_pipeline() -> Dict[str, Any]:
    """Full ML pipeline: loads enriched data, builds negative samples, and trains models."""
    print("Loading enriched physical sites dataset...")
    df_sites = pd.read_parquet(CLEANED_SITES_PARQUET)

    extractor = GeospatialFeatureExtractor()
    extractor.load_layers()
    extractor.set_existing_sites(df_sites)

    print("Generating balanced training dataset...")
    X, y, df_all = prepare_training_data(df_sites, extractor, n_negatives=2500)

    print("Training Suitability Placement Model...")
    suitability_metrics = train_suitability_model(X, y)

    print("\nTraining Equipment & Capacity Recommendation Model...")
    equipment_metrics = train_equipment_recommender(df_sites)

    return {
        "suitability": suitability_metrics,
        "equipment": equipment_metrics,
    }


if __name__ == "__main__":
    train_all_models_pipeline()
