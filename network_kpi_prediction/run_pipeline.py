"""
run_pipeline.py (Root Launcher)
Unified repository-level CLI orchestrator for Network-ML.
Delegates commands to either the 3GPP cellular multi-band pipeline (cellular_kpi_forecast)
or the 4G traffic volume pipeline (traffic_volume_forecast).
"""

import os
import sys
import subprocess
from pathlib import Path

_ROOT = os.path.abspath(os.path.dirname(__file__))
_CELLULAR_PKG = os.path.join(_ROOT, "cellular_kpi_forecast")
_TRAFFIC_PKG = os.path.join(_ROOT, "traffic_volume_forecast")
_ERBS_PKG = os.path.join(_ROOT, "erbs_node_analytics")


DATASET_PRESETS = {
    "earfcndl": os.path.join(_ROOT, "data", "carrier_earfcndl_kpi_daily.csv"),
    "carrier": os.path.join(_ROOT, "data", "carrier_earfcndl_kpi_daily.csv"),
    "summer": os.path.join(_ROOT, "data", "erbs_cell_kpi_summer_120d.csv"),
    "erbs-summer": os.path.join(_ROOT, "data", "erbs_cell_kpi_summer_120d.csv"),
    "full": os.path.join(_ROOT, "data", "erbs_cell_kpi_full_year.csv"),
    "erbs-full": os.path.join(_ROOT, "data", "erbs_cell_kpi_full_year.csv"),
    "macro": os.path.join(_ROOT, "data", "macro_network_kpis_daily.csv"),
    "traffic": os.path.join(_ROOT, "data", "4g_traffic_volume_daily.csv"),
}


def print_root_help():
    print("""
================================================================================
 Network-ML // Unified Telecommunications KPI & Traffic Prediction Engine
================================================================================

Usage:
  python run_pipeline.py [--pipeline PIPELINE] [--dataset DATASET] [COMMAND] [OPTIONS]

Pipelines:
  cellular (default)   3GPP Rel-17 Multi-Band Cellular KPI Forecasting Engine
                       (6 carrier frequency bands x 10 standardized KPIs = 60 series)
  traffic              4G Macro Network Daily Traffic Volume Forecasting Engine
                       (Multi-model tournament, anomaly treatment, 30-day horizon)
  erbs                 Physical ERBS Node Intelligence & Sleeping Cell Auditor
                       (378k rows across 1,067 towers, K-Means clustering, summer stress)

Dataset Presets (--dataset):
  earfcndl / carrier   Ground-truth 6-band EARFCNDL telemetry (carrier_earfcndl_kpi_daily.csv)
  summer / erbs-summer Summer high-density 120-day ERBS telemetry (erbs_cell_kpi_summer_120d.csv)
  full / erbs-full     Full-year 1,067 ERBS base station telemetry (erbs_cell_kpi_full_year.csv)
  macro                Network-wide macro 4G radio KPIs (macro_network_kpis_daily.csv)
  traffic              Daily aggregated 4G data volume in GB (4g_traffic_volume_daily.csv)

Common Commands:
  catalog              Inspect, profile, and synthesize all datasets across 'data/'
  erbs-audit / audit   Full node health profiling, sleeping cell detection, & clustering
  inspect --erbs <ID>  Query instant health scorecard & operational persona for an ERBS node
  gnn / erbs-gnn       Train & benchmark Spatio-Temporal Graph Neural Network (ST-GNN)
  traffic-multi        Train & benchmark multivariate traffic models using macro radio KPIs
  split                Stage 1: Chronological train/val/test data splitting
  train                Stage 2: Feature engineering, model benchmarking & forecasts
  plot                 Stage 3: Publication-grade 300-DPI visual figure generation
  predict              Live inference or precomputed lookup with 90% confidence ribbons

Examples:
  # ERBS node intelligence & Spatial GNN workflows:
  python run_pipeline.py erbs-audit
  python run_pipeline.py inspect --erbs BTWRM1
  python run_pipeline.py gnn

  # Multivariate traffic volume benchmarking:
  python run_pipeline.py traffic-multi

  # Profile all datasets in 'data/':
  python run_pipeline.py catalog

  # Cellular pipeline workflows:
  python run_pipeline.py train --dataset earfcndl
  python run_pipeline.py train --dataset summer --horizon-days 60
  python run_pipeline.py plot --carrier 3500 --kpi dl_throughput_mbps
  python run_pipeline.py predict --carrier 3500 --kpi dl_throughput_mbps --days 7
================================================================================
""")


def main() -> int:
    args = sys.argv[1:]

    # Top-level help check
    if not args or args in [["-h"], ["--help"]]:
        print_root_help()
        return 0

    # Data catalog handler
    if args and args[0] in ["catalog", "analyze-data", "profile-data"]:
        catalog_script = os.path.join(_ROOT, "data_catalog.py")
        res = subprocess.run([sys.executable, catalog_script], cwd=_ROOT)
        return res.returncode

    # ERBS Node Intelligence commands
    if args and args[0] in ["erbs-audit", "audit"]:
        erbs_script = os.path.join(_ERBS_PKG, "run_erbs_analytics.py")
        res = subprocess.run([sys.executable, erbs_script, "audit"] + args[1:], cwd=_ROOT)
        return res.returncode

    if args and args[0] in ["erbs-inspect", "inspect"]:
        erbs_script = os.path.join(_ERBS_PKG, "run_erbs_analytics.py")
        res = subprocess.run([sys.executable, erbs_script, "inspect"] + args[1:], cwd=_ROOT)
        return res.returncode

    if args and args[0] in ["gnn", "erbs-gnn", "spatial-gnn"]:
        erbs_script = os.path.join(_ERBS_PKG, "run_erbs_analytics.py")
        res = subprocess.run([sys.executable, erbs_script, "gnn"] + args[1:], cwd=_ROOT)
        return res.returncode

    # Multivariate Traffic Volume Benchmark command
    if args and args[0] in ["traffic-multi", "multivariate", "multi"]:
        traffic_script = os.path.join(_TRAFFIC_PKG, "run_traffic.py")
        res = subprocess.run([sys.executable, traffic_script, "multivariate"] + args[1:], cwd=_TRAFFIC_PKG)
        return res.returncode

    target_pkg = _CELLULAR_PKG
    target_script = "run_cellular.py"
    explicit_pipeline = False

    # Support optional --dataset preset resolution
    if "--dataset" in args:
        idx = args.index("--dataset")
        if idx + 1 < len(args):
            ds_name = args[idx + 1].lower()
            if ds_name in DATASET_PRESETS:
                resolved_path = DATASET_PRESETS[ds_name]
                print(f"[*] Resolved dataset preset '{ds_name}' -> '{resolved_path}'")
                # Remove --dataset <val> and inject --data-path <resolved_path>
                args = args[:idx] + args[idx + 2:]
                if "--data-path" not in args:
                    args.extend(["--data-path", resolved_path])
            else:
                presets_avail = ", ".join(DATASET_PRESETS.keys())
                print(f"[!] Unknown dataset preset '{ds_name}'. Available: {presets_avail}", file=sys.stderr)
                return 1
        else:
            print("[!] Flag --dataset requires an argument.", file=sys.stderr)
            return 1

    # Support optional pipeline selector
    if "--pipeline" in args:
        idx = args.index("--pipeline")
        if idx + 1 < len(args):
            p_val = args[idx + 1].lower()
            if p_val in ["traffic", "data"]:
                target_pkg = _TRAFFIC_PKG
                target_script = "run_traffic.py"
                explicit_pipeline = True
            elif p_val in ["cellular", "ran", "kpi"]:
                target_pkg = _CELLULAR_PKG
                target_script = "run_cellular.py"
                explicit_pipeline = True
            elif p_val in ["erbs", "nodes", "cell"]:
                target_pkg = _ERBS_PKG
                target_script = "run_erbs_analytics.py"
                explicit_pipeline = True
            elif p_val in ["all", "both"]:
                target_pkg = None
                explicit_pipeline = True
            else:
                print(f"[!] Unknown pipeline '{p_val}'. Choose from: 'cellular' (default), 'traffic', or 'all'.", file=sys.stderr)
                return 1
            # Remove --pipeline <val> from delegated arguments
            args = args[:idx] + args[idx + 2:]
        else:
            print("[!] Flag --pipeline requires an argument ('cellular', 'traffic', or 'all').", file=sys.stderr)
            return 1


    if target_pkg is None:
        # Run across all pipelines
        print("[*] Executing across all pipelines...")
        c_entry = os.path.join(_CELLULAR_PKG, "run_cellular.py")
        t_entry = os.path.join(_TRAFFIC_PKG, "run_traffic.py")
        r1 = subprocess.run([sys.executable, c_entry] + args, cwd=_CELLULAR_PKG)
        r2 = subprocess.run([sys.executable, t_entry] + args, cwd=_TRAFFIC_PKG)
        return 0 if (r1.returncode == 0 and r2.returncode == 0) else 1

    entry_point = os.path.join(target_pkg, target_script)
    cmd = [sys.executable, entry_point] + args

    try:
        res = subprocess.run(cmd, cwd=target_pkg)
        return res.returncode
    except KeyboardInterrupt:
        print("\n[!] Execution interrupted by user.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
