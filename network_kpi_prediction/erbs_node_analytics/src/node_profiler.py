"""node_profiler.py
ERBS Node Health Profiler & Sleeping Cell Anomaly Detector.
Samsung Innovation Campus (SIC) AI Capstone // Team Loop Gain.

Processes 378,631 records across 1,067 physical ERBS base stations.
Calculates 3GPP SLA compliance, composite Health Index (0-100),
and detects multi-metric anomalies (sleeping cells and chronic degradation)
using unsupervised IsolationForest.
"""

from pathlib import Path
from typing import Dict, Any, Tuple, Optional
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler

# 3GPP Rel-17 SLA Reference Targets
SLA_THRESHOLDS = {
    "rrc_setup_sr_min": 99.50,       # Minimum acceptable RRC setup success rate (%)
    "erab_estab_sr_min": 99.50,      # Minimum acceptable E-RAB establishment success rate (%)
    "erab_drop_rate_max": 0.50,      # Maximum acceptable E-RAB drop rate (%)
    "handover_sr_min": 97.50,        # Minimum acceptable handover success rate (%)
    "availability_min": 95.00,       # Minimum acceptable 4G cell availability (%)
    "dl_throughput_target": 10.0,    # Target nominal downlink throughput (Mbps)
    "ul_throughput_target": 1.5,     # Target nominal uplink throughput (Mbps)
}

# Column standard mappings
ERBS_COL_MAPPING = {
    "Date": "date",
    "ERBS Id": "erbs_id",
    "RRC Setup Success Rate": "rrc_setup_sr",
    "E-RAB Establishment Success Rate": "erab_estab_sr",
    "E-RAB Drop Rate": "erab_drop_rate",
    "Handover Success Rate ( 4G Intra System)": "handover_intra_sr",
    "Handover Success Rate": "handover_sr",
    "4G Cell Av. (%)": "cell_availability_pct",
    "E-UTRAN IP Throughput UE DL": "dl_throughput_mbps",
    "E-UTRAN IP Throughput UE UL": "ul_throughput_mbps",
    "Avg RRC Connected users": "connected_users"
}


def load_and_standardize_erbs_data(csv_path: Path | str) -> pd.DataFrame:
    """Loads cell-level ERBS telemetry and applies clean column names and datetime parsing."""
    p = Path(csv_path)
    if not p.exists():
        raise FileNotFoundError(f"ERBS dataset not found at: {p.resolve()}")

    df = pd.read_csv(p)
    df = df.rename(columns=ERBS_COL_MAPPING)
    df["date"] = pd.to_datetime(df["date"])
    df["erbs_id"] = df["erbs_id"].astype(str).str.strip()

    # Fill negligible missing numerical values with median per ERBS or global median
    numeric_cols = [c for c in df.columns if c not in ["date", "erbs_id"]]
    for col in numeric_cols:
        if df[col].isnull().sum() > 0:
            df[col] = df.groupby("erbs_id")[col].transform(lambda s: s.fillna(s.median()))
            df[col] = df[col].fillna(df[col].median())

    return df


def calculate_health_index(df_summary: pd.DataFrame) -> pd.Series:
    """Calculates a bounded composite 3GPP Health Index (0 to 100) per ERBS node.

    Formulation:
      Health = 0.25 * RRC_Score + 0.25 * Drop_Score + 0.25 * Avail_Score + 0.25 * Throughput_Score
    """
    # 1. RRC Setup Component (95% to 100% -> 0 to 100 pts)
    rrc_score = np.clip((df_summary["rrc_setup_sr_mean"] - 95.0) / (100.0 - 95.0) * 100.0, 0, 100)

    # 2. Drop Rate Component (0% to 2% -> 100 down to 0 pts)
    drop_score = np.clip((2.0 - df_summary["erab_drop_rate_mean"]) / 2.0 * 100.0, 0, 100)

    # 3. Availability Component (80% to 100% -> 0 to 100 pts)
    avail_score = np.clip((df_summary["cell_availability_pct_mean"] - 80.0) / (100.0 - 80.0) * 100.0, 0, 100)

    # 4. Throughput Component (0 to 15 Mbps -> 0 to 100 pts)
    tp_score = np.clip(df_summary["dl_throughput_mbps_mean"] / 15.0 * 100.0, 0, 100)

    health = 0.25 * rrc_score + 0.25 * drop_score + 0.25 * avail_score + 0.25 * tp_score
    return health.round(2)


def profile_all_erbs_nodes(
    df: pd.DataFrame, contamination: float = 0.05, random_state: int = 42
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Aggregates all 1,067 physical ERBS nodes, evaluates SLA breach rates,
    calculates composite health scores, and fits an IsolationForest anomaly detector.
    """
    grouped = df.groupby("erbs_id")

    # Aggregate key telemetry metrics per node
    agg_funcs = {
        "rrc_setup_sr": ["mean", "min", "std"],
        "erab_estab_sr": ["mean", "min"],
        "erab_drop_rate": ["mean", "max", "std"],
        "handover_sr": ["mean", "min"],
        "cell_availability_pct": ["mean", "min"],
        "dl_throughput_mbps": ["mean", "min", "max", "std"],
        "ul_throughput_mbps": ["mean", "min"],
        "connected_users": ["mean", "max", "std"],
        "date": ["count"]
    }
    summary = grouped.agg(agg_funcs)
    summary.columns = [f"{col}_{stat}" for col, stat in summary.columns]
    summary = summary.rename(columns={"date_count": "observation_days"}).reset_index()

    # Calculate SLA Violation Flags
    summary["sla_rrc_violation"] = summary["rrc_setup_sr_mean"] < SLA_THRESHOLDS["rrc_setup_sr_min"]
    summary["sla_drop_violation"] = summary["erab_drop_rate_mean"] > SLA_THRESHOLDS["erab_drop_rate_max"]
    summary["sla_avail_violation"] = summary["cell_availability_pct_mean"] < SLA_THRESHOLDS["availability_min"]
    summary["sla_handover_violation"] = summary["handover_sr_mean"] < SLA_THRESHOLDS["handover_sr_min"]
    summary["total_sla_violations"] = (
        summary["sla_rrc_violation"].astype(int) +
        summary["sla_drop_violation"].astype(int) +
        summary["sla_avail_violation"].astype(int) +
        summary["sla_handover_violation"].astype(int)
    )

    # Compute Composite Health Index
    summary["health_index"] = calculate_health_index(summary)

    # Sleeping Cell Heuristic: High availability but abnormally low throughput & users or high drop
    summary["is_sleeping_cell_heuristic"] = (
        (summary["cell_availability_pct_mean"] >= 90.0) &
        (
            (summary["dl_throughput_mbps_mean"] < 2.0) |
            (summary["erab_drop_rate_mean"] > 1.0) |
            (summary["rrc_setup_sr_mean"] < 98.0)
        )
    )

    # Unsupervised Anomaly Detection using Isolation Forest
    feature_cols_for_iso = [
        "rrc_setup_sr_mean", "erab_drop_rate_mean", "cell_availability_pct_mean",
        "dl_throughput_mbps_mean", "ul_throughput_mbps_mean", "connected_users_mean"
    ]
    scaler = RobustScaler()
    X_scaled = scaler.fit_transform(summary[feature_cols_for_iso].fillna(0))

    iso = IsolationForest(
        contamination=contamination,
        random_state=random_state,
        n_estimators=150,
        n_jobs=-1
    )
    iso_labels = iso.fit_predict(X_scaled)
    iso_scores = iso.decision_function(X_scaled)

    summary["is_anomaly_isolation_forest"] = (iso_labels == -1)
    summary["anomaly_score"] = iso_scores.round(4)

    # Combined Flag: Sleeping cell confirmed if heuristic or high isolation forest confidence
    summary["is_sleeping_cell"] = (
        summary["is_sleeping_cell_heuristic"] | summary["is_anomaly_isolation_forest"]
    )

    # Rank worst-performing degraded towers
    summary["degradation_rank"] = summary["health_index"].rank(ascending=True, method="dense").astype(int)

    # High-level stats
    stats = {
        "total_nodes": int(len(summary)),
        "total_observations": int(len(df)),
        "mean_health_index": float(summary["health_index"].mean()),
        "median_health_index": float(summary["health_index"].median()),
        "healthy_nodes_count": int((summary["health_index"] >= 80.0).sum()),
        "moderate_risk_count": int(((summary["health_index"] >= 60.0) & (summary["health_index"] < 80.0)).sum()),
        "severe_degraded_count": int((summary["health_index"] < 60.0).sum()),
        "sleeping_cells_detected": int(summary["is_sleeping_cell"].sum()),
        "sla_compliant_nodes_count": int((summary["total_sla_violations"] == 0).sum()),
        "rrc_breaches": int(summary["sla_rrc_violation"].sum()),
        "drop_rate_breaches": int(summary["sla_drop_violation"].sum()),
        "availability_breaches": int(summary["sla_avail_violation"].sum()),
    }

    return summary.sort_values("health_index", ascending=True).reset_index(drop=True), stats
