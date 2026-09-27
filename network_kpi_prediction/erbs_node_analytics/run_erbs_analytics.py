"""run_erbs_analytics.py
Master Orchestrator & CLI for Physical ERBS Node Intelligence.
Samsung Innovation Campus (SIC) AI Capstone // Team Loop Gain.

Commands:
  audit     Execute end-to-end node health profiling, sleeping cell detection,
            behavioral clustering, summer stress benchmarking, and export synergy datasets.
  inspect   Display live engineering diagnostic scorecard and operational persona for a specific ERBS node.
"""

import os
import sys
import json
import argparse
from pathlib import Path
import pandas as pd

# Package path resolution
_PKG_ROOT = Path(__file__).resolve().parent
_REPO_ROOT = _PKG_ROOT.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.node_profiler import load_and_standardize_erbs_data, profile_all_erbs_nodes
from src.node_clustering import build_clustering_features, perform_erbs_clustering
from src.summer_stress import compute_summer_stress_benchmark
from src.export_synergy import export_cross_subsystem_targets
from src.visualizer import (
    plot_erbs_clusters, plot_health_distribution,
    plot_sleeping_cells_top20, plot_summer_stress
)

_DATA_DIR = _REPO_ROOT / "data"
DEFAULT_FULL_YEAR_CSV = _DATA_DIR / "erbs_cell_kpi_full_year.csv"
DEFAULT_SUMMER_CSV = _DATA_DIR / "erbs_cell_kpi_summer_120d.csv"
DEFAULT_OUT_DIR = _PKG_ROOT / "output"
DEFAULT_PLOT_DIR = _PKG_ROOT / "plots"


def run_full_erbs_audit(
    full_csv: Path | str = DEFAULT_FULL_YEAR_CSV,
    summer_csv: Path | str = DEFAULT_SUMMER_CSV,
    output_dir: Path | str = DEFAULT_OUT_DIR,
    plot_dir: Path | str = DEFAULT_PLOT_DIR,
    dpi: int = 300,
) -> dict:
    """Executes the full pipeline across all 378,631 ERBS records."""
    out_dir = Path(output_dir)
    p_dir = Path(plot_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    p_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 95)
    print("NETWORK-ML // PHYSICAL ERBS NODE INTELLIGENCE & SLEEPING CELL AUDITOR")
    print("Datasets: Full-Year (378k rows) & Peak Summer Window (125k rows)")
    print("=" * 95)

    # 1. Load Data
    print(f"\n[1/5] Ingesting full-year ERBS telemetry: {Path(full_csv).name}...")
    full_df = load_and_standardize_erbs_data(full_csv)
    print(f"      Ingested {len(full_df):,} records across {full_df['erbs_id'].nunique():,} unique base stations.")

    print(f"\n[2/5] Profiling SLA compliance & detecting sleeping cells via IsolationForest...")
    profile_df, prof_stats = profile_all_erbs_nodes(full_df)
    profile_out = out_dir / "erbs_node_health_scorecard.csv"
    profile_df.to_csv(profile_out, index=False)
    print(f"      Mean Health Index: {prof_stats['mean_health_index']:.2f} / 100")
    print(f"      Healthy Nodes: {prof_stats['healthy_nodes_count']} | Moderate Risk: {prof_stats['moderate_risk_count']} | Severe Degraded: {prof_stats['severe_degraded_count']}")
    print(f"      Verified Sleeping Cells Flagged: {prof_stats['sleeping_cells_detected']}")

    # 2. Behavioral Clustering
    print(f"\n[3/5] Performing Behavioral Clustering & PCA Persona Extraction...")
    feat_df = build_clustering_features(full_df)
    cluster_df, cluster_meta = perform_erbs_clustering(feat_df)
    cluster_out = out_dir / "erbs_behavioral_clusters.csv"
    cluster_df.to_csv(cluster_out, index=False)
    print(f"      Optimal Clusters: k={cluster_meta['optimal_k']} (Silhouette: {cluster_meta['optimal_silhouette_score']:.3f})")
    for cid, info in cluster_meta["cluster_profiles"].items():
        print(f"      - Cluster {cid} [{info['persona']}]: {info['node_count']} nodes ({info['pct_of_network']}%)")

    # 3. Summer Stress Benchmarking
    print(f"\n[4/5] Evaluating Summer Thermal & Capacity Degradation: {Path(summer_csv).name}...")
    summer_df = load_and_standardize_erbs_data(summer_csv)
    stress_df, stress_stats = compute_summer_stress_benchmark(full_df, summer_df)
    stress_out = out_dir / "erbs_summer_stress_benchmark.csv"
    stress_df.to_csv(stress_out, index=False)
    print(f"      Summer Throttled / Overloaded Nodes: {stress_stats['summer_throttled_nodes']}")
    print(f"      Summer Surge Hotspots (>30% traffic growth): {stress_stats['summer_surge_nodes']}")

    # 4. Cross-Subsystem Synergy Export
    print(f"\n[5/5] Exporting Cross-Subsystem Bridge Datasets & Publication Plots...")
    synergy_res = export_cross_subsystem_targets(profile_df, cluster_df, out_dir)
    print(f"      [+] Antenna Placement Congestion Targets: {synergy_res['antenna_targets_count']} nodes -> {Path(synergy_res['antenna_targets_path']).name}")
    print(f"      [+] Customer Churn Risk Targets: {synergy_res['churn_targets_count']} nodes -> {Path(synergy_res['churn_targets_path']).name}")

    # Generate Publication Plots
    plot_erbs_clusters(cluster_df, cluster_meta, p_dir / "01_erbs_cluster_pca.png", dpi=dpi)
    plot_health_distribution(profile_df, prof_stats, p_dir / "02_erbs_health_distribution.png", dpi=dpi)
    plot_sleeping_cells_top20(profile_df, p_dir / "03_erbs_sleeping_cells_top20.png", dpi=dpi)
    plot_summer_stress(stress_df, stress_stats, p_dir / "04_erbs_summer_stress_benchmark.png", dpi=dpi)
    print(f"      [+] Generated 4 publication-grade 300-DPI charts in: {p_dir.resolve()}")

    audit_summary = {
        "profiling_stats": prof_stats,
        "clustering_metadata": cluster_meta,
        "summer_stress_stats": stress_stats,
        "cross_subsystem_exports": synergy_res
    }
    with open(out_dir / "erbs_audit_summary.json", "w", encoding="utf-8") as f:
        json.dump(audit_summary, f, indent=2)

    print("\n" + "=" * 95)
    print(f"ERBS Node Intelligence Audit Complete. Outputs saved to: {out_dir.resolve()}")
    print("=" * 95)
    return audit_summary


def inspect_single_erbs(erbs_id: str, output_dir: Path | str = DEFAULT_OUT_DIR) -> int:
    """Displays instant diagnostic health card for a requested ERBS ID."""
    out_dir = Path(output_dir)
    scorecard_path = out_dir / "erbs_node_health_scorecard.csv"
    cluster_path = out_dir / "erbs_behavioral_clusters.csv"
    stress_path = out_dir / "erbs_summer_stress_benchmark.csv"

    if not scorecard_path.exists():
        print("[!] Audit database not found. Running audit first...")
        run_full_erbs_audit(output_dir=out_dir)

    df_score = pd.read_csv(scorecard_path)
    match_score = df_score[df_score["erbs_id"].str.upper() == erbs_id.strip().upper()]

    if match_score.empty:
        print(f"[!] ERBS ID '{erbs_id}' not found in network telemetry. Available sample: {df_score['erbs_id'].head(5).tolist()}")
        return 1

    row = match_score.iloc[0]
    erbs_clean = str(row["erbs_id"])

    # Cluster persona
    persona = "Unclassified"
    if cluster_path.exists():
        df_c = pd.read_csv(cluster_path)
        c_match = df_c[df_c["erbs_id"] == erbs_clean]
        if not c_match.empty:
            persona = str(c_match.iloc[0]["operational_persona"])

    # Summer stress
    summer_throttle = "Normal"
    if stress_path.exists():
        df_s = pd.read_csv(stress_path)
        s_match = df_s[df_s["erbs_id"] == erbs_clean]
        if not s_match.empty:
            if s_match.iloc[0]["is_summer_throttled"]:
                summer_throttle = "SEVERE THERMAL / CAPACITY THROTTLING"
            elif s_match.iloc[0]["is_summer_surge_hub"]:
                summer_throttle = "HIGH SUMMER VACATION SURGE"

    h = row["health_index"]
    status_label = "EXCELLENT / COMPLIANT" if h >= 80 else ("DEGRADED / RISK" if h >= 60 else "CRITICAL / SLEEPING CELL")

    print("\n" + "=" * 70)
    print(f" [3GPP BASE STATION DIAGNOSTIC CARD] Node: {erbs_clean}")
    print("=" * 70)
    print(f" Operational Persona:    {persona}")
    print(f" Composite Health Index: {h:.1f} / 100 ({status_label})")
    print(f" Network Health Rank:    #{int(row['degradation_rank'])} of {len(df_score)} (1 = Worst)")
    print(f" Sleeping Cell Status:   {'[ALERT] YES (Anomaly Detected)' if row['is_sleeping_cell'] else '[OK] Normal'}")
    print(f" Total SLA Breaches:     {int(row['total_sla_violations'])}")
    print(f" Summer Season Status:   {summer_throttle}")
    print("-" * 70)
    print(" Key Telemetry Metrics:")
    print(f"   * RRC Setup Success Rate:    {row['rrc_setup_sr_mean']:.2f}% (Min: {row['rrc_setup_sr_min']:.2f}%)")
    print(f"   * E-RAB Establishment SR:    {row['erab_estab_sr_mean']:.2f}%")
    print(f"   * E-RAB Drop Rate:           {row['erab_drop_rate_mean']:.2f}% (Max: {row['erab_drop_rate_max']:.2f}%)")
    print(f"   * Cell Availability:         {row['cell_availability_pct_mean']:.2f}%")
    print(f"   * Downlink Throughput:       {row['dl_throughput_mbps_mean']:.2f} Mbps (Max: {row['dl_throughput_mbps_max']:.2f} Mbps)")
    print(f"   * Uplink Throughput:         {row['ul_throughput_mbps_mean']:.2f} Mbps")
    print(f"   * Active Connected Users:    {row['connected_users_mean']:.1f} (Max: {row['connected_users_max']:.1f})")
    print("=" * 70)

    # Engineering Action recommendation
    if row["is_sleeping_cell"] or h < 60:
        print(" [ACTION REQUIRED] Dispatch field RF technician for hardware diagnostic,")
        print("     inspect remote radio head (RRH) and check fiber backhaul link.")
    elif h < 80:
        print(" [ACTION REQUIRED] Re-tune antenna electrical downtilt and evaluate")
        print("     neighbor relations to mitigate handover / drop rate violations.")
    else:
        print(" [STATUS] Routine telemetry monitoring. No maintenance required.")
    print("=" * 70 + "\n")
    return 0


def main():
    parser = argparse.ArgumentParser(description="ERBS Physical Node Analytics & Sleeping Cell Auditor")
    subparsers = parser.add_subparsers(dest="command", help="Subcommand to execute")

    # audit subcommand
    audit_parser = subparsers.add_parser("audit", help="Run full ERBS node intelligence audit")
    audit_parser.add_argument("--full-csv", default=str(DEFAULT_FULL_YEAR_CSV), help="Path to full-year ERBS CSV")
    audit_parser.add_argument("--summer-csv", default=str(DEFAULT_SUMMER_CSV), help="Path to summer ERBS CSV")
    audit_parser.add_argument("--output-dir", default=str(DEFAULT_OUT_DIR), help="Output directory")
    audit_parser.add_argument("--plot-dir", default=str(DEFAULT_PLOT_DIR), help="Plot directory")

    # inspect subcommand
    inspect_parser = subparsers.add_parser("inspect", help="Inspect single ERBS node")
    inspect_parser.add_argument("--erbs", required=True, help="ERBS Node ID (e.g. BTWRM1)")
    inspect_parser.add_argument("--output-dir", default=str(DEFAULT_OUT_DIR), help="Output directory containing scorecard")

    args = parser.parse_args()
    if args.command == "inspect":
        sys.exit(inspect_single_erbs(args.erbs, output_dir=args.output_dir))
    else:
        run_full_erbs_audit(
            full_csv=args.full_csv if hasattr(args, "full_csv") else DEFAULT_FULL_YEAR_CSV,
            summer_csv=args.summer_csv if hasattr(args, "summer_csv") else DEFAULT_SUMMER_CSV,
            output_dir=args.output_dir if hasattr(args, "output_dir") else DEFAULT_OUT_DIR,
            plot_dir=args.plot_dir if hasattr(args, "plot_dir") else DEFAULT_PLOT_DIR,
        )


if __name__ == "__main__":
    main()
