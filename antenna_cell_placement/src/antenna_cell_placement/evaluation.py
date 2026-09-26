"""
Geographic (municipality-held-out) evaluation of the cell-placement models.

The shipped training code reports out-of-fold scores from random 5-fold CV, which
lets neighbouring sites of one municipality land on both sides of a split, and it
scores the equipment recommender on its own training data. This module measures
both models the way they will actually be used, on regions they never saw, and
stress-tests the suitability model against hard negatives (populated locations
that are near, but not at, an existing site). Nothing here overwrites shipped
models or reports.
"""

import json
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, average_precision_score, f1_score, roc_auc_score
from sklearn.model_selection import GroupKFold, StratifiedKFold

from antenna_cell_placement.config import CLEANED_SITES_PARQUET, LIBYA_BBOX, REPORTS_DIR
from antenna_cell_placement.feature_engineering import GeospatialFeatureExtractor
from antenna_cell_placement.placement_model import (
    EQUIPMENT_FEATURE_COLS,
    SUITABILITY_FEATURE_COLS,
    generate_synthetic_negative_samples,
    label_equipment_tiers,
)

EVALUATION_REPORT_PATH = REPORTS_DIR / "honest_evaluation.json"

LGB_PARAMS = dict(
    n_estimators=350, learning_rate=0.035, max_depth=6, num_leaves=31,
    subsample=0.8, colsample_bytree=0.8, random_state=42, verbose=-1,
)

METERS_PER_DEGREE_LAT = 111_320.0


def binary_metrics(y_true, prob, threshold: float = 0.5) -> Dict[str, float]:
    """ROC-AUC, average precision, accuracy and F1 for a probability vector."""
    y_true = np.asarray(y_true)
    prob = np.asarray(prob)
    pred = (prob >= threshold).astype(int)
    return {
        "roc_auc": float(roc_auc_score(y_true, prob)),
        "average_precision": float(average_precision_score(y_true, prob)),
        "accuracy": float(accuracy_score(y_true, pred)),
        "f1": float(f1_score(y_true, pred)),
        "n": int(len(y_true)),
        "n_positive": int(y_true.sum()),
    }


def select_test_municipalities(
    site_municipalities: pd.Series, share: float = 0.2, max_share: float = 0.3, seed: int = 42,
) -> List[str]:
    """
    Pick whole municipalities to hold out as the final test set: shuffled with a
    fixed seed, added until they cover `share` of the sites, skipping any that would
    push the hold-out above `max_share` (so one huge city cannot swallow the split).
    """
    counts = site_municipalities.fillna("Unknown").value_counts()
    total = int(counts.sum())
    order = list(counts.index)
    np.random.default_rng(seed).shuffle(order)

    chosen, covered = [], 0
    for name in order:
        if covered >= share * total:
            break
        if covered + counts[name] <= max_share * total:
            chosen.append(name)
            covered += int(counts[name])
    return chosen


def offset_points(lons, lats, distances_m, bearings_rad) -> Tuple[np.ndarray, np.ndarray]:
    """Move points by a distance and bearing (small-distance flat-earth approximation)."""
    lons, lats = np.asarray(lons, dtype=float), np.asarray(lats, dtype=float)
    d_lat = np.asarray(distances_m) * np.cos(bearings_rad) / METERS_PER_DEGREE_LAT
    d_lon = np.asarray(distances_m) * np.sin(bearings_rad) / (METERS_PER_DEGREE_LAT * np.cos(np.radians(lats)))
    return lons + d_lon, lats + d_lat


def generate_hard_negatives(
    df_sites: pd.DataFrame,
    extractor: GeospatialFeatureExtractor,
    n: int = 1500,
    min_dist_m: float = 500.0,
    max_dist_m: float = 3000.0,
    min_population_5km: float = 300.0,
    seed: int = 7,
) -> pd.DataFrame:
    """
    Populated locations 0.5-3 km from an existing site that are not themselves sites.
    A model that only learned "populated and near the network" cannot separate these
    from real sites, so scoring them exposes how much the easy benchmark hides.
    """
    rng = np.random.default_rng(seed)
    base = df_sites.sample(n=min(len(df_sites) * 5, n * 4), replace=True, random_state=seed)
    lons, lats = offset_points(
        base["canonical_longitude"].values,
        base["canonical_latitude"].values,
        rng.uniform(min_dist_m, max_dist_m, len(base)),
        rng.uniform(0, 2 * np.pi, len(base)),
    )
    inside = (
        (LIBYA_BBOX["min_lon"] <= lons) & (lons <= LIBYA_BBOX["max_lon"])
        & (LIBYA_BBOX["min_lat"] <= lats) & (lats <= LIBYA_BBOX["max_lat"])
    )
    feats = extractor.extract_features(lons[inside], lats[inside], is_existing_site=False)
    keep = (
        feats["dist_to_nearest_site_m"].between(min_dist_m, max_dist_m)
        & (feats["population_sum_5km"] >= min_population_5km)
        & feats["municipality_name"].isin(df_sites["municipality_name"].dropna().unique())
    )
    feats = feats[keep].head(n).copy()
    feats["is_cell_site"] = 0
    return feats


def build_suitability_dataset(df_sites: pd.DataFrame, extractor: GeospatialFeatureExtractor, n_negatives: int = 2500) -> pd.DataFrame:
    """Positives (real sites) and the shipped synthetic negatives, with municipality labels."""
    positives = df_sites.copy()
    positives["is_cell_site"] = 1
    negatives = generate_synthetic_negative_samples(positives, extractor, n_negatives=n_negatives)
    cols = SUITABILITY_FEATURE_COLS + ["is_cell_site", "municipality_name"]
    data = pd.concat([positives[cols], negatives[cols]], ignore_index=True)
    data["municipality_name"] = data["municipality_name"].fillna("Unknown")
    return data


def _oof_predictions(X: pd.DataFrame, y: pd.Series, splitter, groups=None) -> Tuple[np.ndarray, List[float]]:
    oof = np.zeros(len(y))
    fold_aucs: List[float] = []
    for train_idx, test_idx in splitter.split(X, y, groups):
        model = LGBMClassifier(**LGB_PARAMS).fit(X.iloc[train_idx], y.iloc[train_idx])
        oof[test_idx] = model.predict_proba(X.iloc[test_idx])[:, 1]
        if y.iloc[test_idx].nunique() == 2:
            fold_aucs.append(float(roc_auc_score(y.iloc[test_idx], oof[test_idx])))
    return oof, fold_aucs


def evaluate_suitability(df_sites: pd.DataFrame, extractor: GeospatialFeatureExtractor) -> Dict[str, object]:
    """Random CV vs municipality-grouped CV vs a final municipality hold-out, plus a hard-negative stress test."""
    data = build_suitability_dataset(df_sites, extractor)
    X, y, groups = data[SUITABILITY_FEATURE_COLS], data["is_cell_site"], data["municipality_name"]

    print("Suitability: random stratified 5-fold CV (the shipped scheme)...")
    oof_random, _ = _oof_predictions(X, y, StratifiedKFold(5, shuffle=True, random_state=42))

    print("Suitability: municipality-grouped 5-fold CV...")
    oof_group, group_fold_aucs = _oof_predictions(X, y, GroupKFold(5), groups)

    test_munis = select_test_municipalities(data.loc[y == 1, "municipality_name"])
    is_test = groups.isin(test_munis).values
    print(f"Suitability: final hold-out of {len(test_munis)} municipalities: {test_munis}")
    model = LGBMClassifier(**LGB_PARAMS).fit(X[~is_test], y[~is_test])
    test_prob = model.predict_proba(X[is_test])[:, 1]
    held_out = binary_metrics(y[is_test], test_prob)
    baseline_pop = float(roc_auc_score(y[is_test], X.loc[is_test, "population_sum_5km"]))

    print("Suitability: hard-negative stress test on the held-out municipalities...")
    test_sites = df_sites[df_sites["municipality_name"].isin(test_munis)]
    hard = generate_hard_negatives(test_sites, extractor)
    stress = None
    if len(hard) >= 50 and len(test_sites) >= 20:
        pos_prob = model.predict_proba(test_sites[SUITABILITY_FEATURE_COLS])[:, 1]
        hard_prob = model.predict_proba(hard[SUITABILITY_FEATURE_COLS])[:, 1]
        labels = np.r_[np.ones(len(pos_prob)), np.zeros(len(hard_prob))]
        scores = np.r_[pos_prob, hard_prob]
        pops = np.r_[test_sites["population_sum_5km"].values, hard["population_sum_5km"].values]
        stress = {
            "n_real_sites": int(len(pos_prob)),
            "n_hard_negatives": int(len(hard_prob)),
            "roc_auc": float(roc_auc_score(labels, scores)),
            "population_only_roc_auc": float(roc_auc_score(labels, pops)),
            "mean_score_real_sites": float(pos_prob.mean()),
            "mean_score_hard_negatives": float(hard_prob.mean()),
            "hard_negatives_scored_above_0_5": float((hard_prob >= 0.5).mean()),
        }

    return {
        "n_samples": int(len(data)),
        "n_sites": int(y.sum()),
        "random_cv": binary_metrics(y, oof_random),
        "municipality_grouped_cv": {**binary_metrics(y, oof_group), "fold_roc_auc": group_fold_aucs},
        "held_out_test": {
            "municipalities": test_munis,
            **held_out,
            "population_only_baseline_roc_auc": baseline_pop,
        },
        "hard_negative_stress_test": stress,
    }


def evaluate_equipment(df_sites: pd.DataFrame) -> Dict[str, object]:
    """Held-out accuracy of the equipment recommender against honest baselines."""
    df = df_sites.copy()
    df["municipality_name"] = df["municipality_name"].fillna("Unknown")
    y = label_equipment_tiers(df)
    X = df[EQUIPMENT_FEATURE_COLS]

    def forest():
        return RandomForestClassifier(n_estimators=200, max_depth=8, random_state=42)

    in_sample = float(accuracy_score(y, forest().fit(X, y).predict(X)))

    def cv_scores(splitter, groups=None):
        pred = np.empty(len(y), dtype=object)
        for train_idx, test_idx in splitter.split(X, y, groups):
            pred[test_idx] = forest().fit(X.iloc[train_idx], y.iloc[train_idx]).predict(X.iloc[test_idx])
        return {
            "accuracy": float(accuracy_score(y, pred)),
            "macro_f1": float(f1_score(y, pred, average="macro")),
        }

    # Rules the model can see: label the sites using only the feature-side inputs.
    feature_only = df.assign(primary_tower_type="MACRO", total_bandwidth_mhz=0.0, total_carrier_count=0)
    feature_rule_accuracy = float(accuracy_score(y, label_equipment_tiers(feature_only)))

    return {
        "class_counts": y.value_counts().to_dict(),
        "majority_class_baseline_accuracy": float(y.value_counts(normalize=True).iloc[0]),
        "feature_side_rules_only_accuracy": feature_rule_accuracy,
        "in_sample_accuracy_as_shipped": in_sample,
        "random_cv": cv_scores(StratifiedKFold(5, shuffle=True, random_state=42)),
        "municipality_grouped_cv": cv_scores(GroupKFold(5), df["municipality_name"]),
    }


def run_evaluation_pipeline() -> Dict[str, object]:
    """Run both evaluations on the enriched site table and write the JSON report."""
    print("Loading enriched physical sites...")
    df_sites = pd.read_parquet(CLEANED_SITES_PARQUET)

    extractor = GeospatialFeatureExtractor()
    extractor.load_layers()
    extractor.set_existing_sites(df_sites)

    report = {
        "suitability_model": evaluate_suitability(df_sites, extractor),
        "equipment_model": evaluate_equipment(df_sites),
    }

    EVALUATION_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EVALUATION_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"Exported evaluation report to: {EVALUATION_REPORT_PATH}")
    return report


if __name__ == "__main__":
    run_evaluation_pipeline()
