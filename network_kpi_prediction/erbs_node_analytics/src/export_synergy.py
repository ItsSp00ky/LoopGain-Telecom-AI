"""export_synergy.py
Cross-Subsystem Data Bridge & Synergy Exporter.
Samsung Innovation Campus (SIC) AI Capstone // Team Loop Gain.

Bridges Network KPI Prediction with:
1. Antenna Cell Placement: Exports high-priority congestion hotspots for new site rollout.
2. Customer Churn Prediction: Exports chronically degraded towers driving customer dissatisfaction.
"""

from pathlib import Path
from typing import Dict, Any, Tuple
import pandas as pd


def export_cross_subsystem_targets(
    profile_df: pd.DataFrame,
    cluster_df: pd.DataFrame,
    output_dir: Path | str
) -> Dict[str, str]:
    """Generates cross-domain export datasets connecting Network-ML to Antenna Placement and Churn."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    merged = pd.merge(
        profile_df,
        cluster_df[["erbs_id", "cluster_id", "operational_persona", "weekend_to_weekday_ratio"]],
        on="erbs_id"
    )

    # 1. Targets for Antenna Cell Placement (New site planning & beam optimization)
    # Condition: High users, congested throughput, or capacity exhaustion
    antenna_targets = merged[
        (merged["connected_users_mean"] >= 18.0) |
        (merged["dl_throughput_mbps_mean"] < 6.0) |
        (merged["operational_persona"].str.contains("Congested|Transit", case=False, na=False))
    ].copy()
    antenna_targets["antenna_recommendation_priority"] = (
        (antenna_targets["connected_users_mean"] / 10.0) +
        (10.0 / (antenna_targets["dl_throughput_mbps_mean"] + 0.1)) +
        (antenna_targets["total_sla_violations"] * 2.0)
    ).round(2)
    antenna_targets = antenna_targets.sort_values("antenna_recommendation_priority", ascending=False)
    antenna_cols = [
        "erbs_id", "antenna_recommendation_priority", "connected_users_mean",
        "dl_throughput_mbps_mean", "erab_drop_rate_mean", "operational_persona",
        "health_index", "total_sla_violations"
    ]
    antenna_file = out_path / "erbs_congestion_hotspots_for_antenna_placement.csv"
    antenna_targets[antenna_cols].to_csv(antenna_file, index=False)

    # 2. Targets for Customer Churn Prediction (Retention intervention)
    # Condition: Low health index (< 70), high drop rate (> 0.4%), or sleeping cell
    churn_targets = merged[
        (merged["health_index"] < 75.0) |
        (merged["erab_drop_rate_mean"] > 0.40) |
        (merged["is_sleeping_cell"])
    ].copy()
    churn_targets["churn_risk_weight"] = (
        (100.0 - churn_targets["health_index"]) * 0.5 +
        (churn_targets["erab_drop_rate_mean"] * 30.0) +
        (churn_targets["is_sleeping_cell"].astype(int) * 20.0)
    ).round(2)
    churn_targets = churn_targets.sort_values("churn_risk_weight", ascending=False)
    churn_cols = [
        "erbs_id", "churn_risk_weight", "health_index", "erab_drop_rate_mean",
        "cell_availability_pct_mean", "dl_throughput_mbps_mean", "is_sleeping_cell",
        "operational_persona"
    ]
    churn_file = out_path / "erbs_severe_quality_degradation_for_churn.csv"
    churn_targets[churn_cols].to_csv(churn_file, index=False)

    return {
        "antenna_targets_path": str(antenna_file.resolve()),
        "antenna_targets_count": len(antenna_targets),
        "churn_targets_path": str(churn_file.resolve()),
        "churn_targets_count": len(churn_targets),
    }
