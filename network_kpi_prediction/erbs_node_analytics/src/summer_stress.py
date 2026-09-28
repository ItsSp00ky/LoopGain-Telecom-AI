"""summer_stress.py
Summer Peak Stress & Thermal Load Benchmarking Module.
Samsung Innovation Campus (SIC) AI Capstone // Team Loop Gain.

Contrasts the 120-day high-density summer window against full-year telemetry.
Quantifies thermal throttling, summer overload, and seasonal operational stress.
"""

from pathlib import Path
from typing import Dict, Any, Tuple
import pandas as pd
import numpy as np


def compute_summer_stress_benchmark(
    full_df: pd.DataFrame,
    summer_df: pd.DataFrame
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Evaluates summer vs baseline operational stress per ERBS node."""
    # Group full-year baseline
    full_summary = full_df.groupby("erbs_id").agg(
        baseline_dl_tp=("dl_throughput_mbps", "mean"),
        baseline_ul_tp=("ul_throughput_mbps", "mean"),
        baseline_drop_rate=("erab_drop_rate", "mean"),
        baseline_users=("connected_users", "mean"),
        baseline_avail=("cell_availability_pct", "mean"),
        baseline_rrc_sr=("rrc_setup_sr", "mean"),
    ).reset_index()

    # Group summer window
    summer_summary = summer_df.groupby("erbs_id").agg(
        summer_dl_tp=("dl_throughput_mbps", "mean"),
        summer_ul_tp=("ul_throughput_mbps", "mean"),
        summer_drop_rate=("erab_drop_rate", "mean"),
        summer_users=("connected_users", "mean"),
        summer_avail=("cell_availability_pct", "mean"),
        summer_rrc_sr=("rrc_setup_sr", "mean"),
    ).reset_index()

    merged = pd.merge(full_summary, summer_summary, on="erbs_id", how="inner")

    # Calculate Deltas
    merged["delta_dl_throughput_mbps"] = (merged["summer_dl_tp"] - merged["baseline_dl_tp"]).round(3)
    merged["delta_drop_rate"] = (merged["summer_drop_rate"] - merged["baseline_drop_rate"]).round(3)
    merged["delta_availability_pct"] = (merged["summer_avail"] - merged["baseline_avail"]).round(3)
    merged["delta_connected_users"] = (merged["summer_users"] - merged["baseline_users"]).round(3)
    merged["delta_users_pct"] = (
        (merged["delta_connected_users"] / (merged["baseline_users"] + 1e-4)) * 100.0
    ).round(2)

    # Stress Flags
    # 1. Thermal / Congestion Throttle: Downlink drops by > 2 Mbps and Drop rate increases
    merged["is_summer_throttled"] = (
        (merged["delta_dl_throughput_mbps"] < -1.5) &
        (merged["delta_drop_rate"] > 0.05)
    )

    # 2. Summer Surge Hotspot: User increase > 30%
    merged["is_summer_surge_hub"] = merged["delta_users_pct"] > 30.0

    # 3. Summer Downtime Sensitive: Availability drops by > 3%
    merged["is_summer_downtime_sensitive"] = merged["delta_availability_pct"] < -3.0

    # Overall Stress Score (0 to 100; higher = more severe summer deterioration)
    # Penalize drop increases, availability drops, and throughput drops
    drop_pen = np.clip(merged["delta_drop_rate"] / 0.5 * 40.0, 0, 40)
    avail_pen = np.clip(-merged["delta_availability_pct"] / 5.0 * 30.0, 0, 30)
    tp_pen = np.clip(-merged["delta_dl_throughput_mbps"] / 5.0 * 30.0, 0, 30)
    merged["summer_stress_score"] = (drop_pen + avail_pen + tp_pen).round(2)

    stats = {
        "common_erbs_nodes": int(len(merged)),
        "summer_throttled_nodes": int(merged["is_summer_throttled"].sum()),
        "summer_surge_nodes": int(merged["is_summer_surge_hub"].sum()),
        "summer_downtime_sensitive_nodes": int(merged["is_summer_downtime_sensitive"].sum()),
        "mean_summer_stress_score": float(merged["summer_stress_score"].mean()),
        "max_summer_stress_score": float(merged["summer_stress_score"].max()),
        "top_throttled_nodes_sample": merged[merged["is_summer_throttled"]]["erbs_id"].head(5).tolist()
    }

    return merged.sort_values("summer_stress_score", ascending=False).reset_index(drop=True), stats
