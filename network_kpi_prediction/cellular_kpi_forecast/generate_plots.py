"""
plot.py
Stage 3: Publication-Grade 300-DPI Plot Generation Engine (Light Theme).
Executes batch or selective generation of clean light publication plots across all 6 bands and 10 KPIs.
"""

import os
import sys
import argparse
import pandas as pd
import json

_REPO_ROOT = os.path.abspath(os.path.dirname(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.visualization import generate_all_plots, plot_single_kpi, plot_carrier_grid, plot_multiband_kpi
from src.kpi_config import CARRIER_BANDS, KPI_KEYS


def resolve_file(filename: str) -> str:
    """Resolves data paths checking root and data/ subfolder."""
    candidates = [
        os.path.join(_REPO_ROOT, filename),
        os.path.join(_REPO_ROOT, "data", filename),
        os.path.join(_REPO_ROOT, "data", "output", filename),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return candidates[0]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Network-ML // Stage 3: Publication-Grade Telemetry Plot Generator"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=os.path.join(_REPO_ROOT, "plots"),
        help="Directory to save core overview plots (default: ./plots)"
    )
    parser.add_argument(
        "--artifacts-dir",
        type=str,
        default=os.path.join(_REPO_ROOT, "artifacts"),
        help="Directory to save standalone artifacts and index manifest (default: ./artifacts)"
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="Plot resolution DPI (default: 300 for publication grade)"
    )
    parser.add_argument(
        "--carrier",
        type=int,
        choices=CARRIER_BANDS,
        default=None,
        help="Generate only for specified carrier frequency band (e.g. 350)"
    )
    parser.add_argument(
        "--kpi",
        type=str,
        choices=KPI_KEYS,
        default=None,
        help="Generate only for specified 3GPP KPI key"
    )
    parser.add_argument(
        "--clean-csv",
        type=str,
        default=None,
        help="Custom path to clean historical telemetry CSV"
    )
    parser.add_argument(
        "--forecast-csv",
        type=str,
        default=None,
        help="Custom path to forecast CSV"
    )
    parser.add_argument(
        "--metrics-json",
        type=str,
        default=None,
        help="Custom path to model metrics JSON"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress verbose progress logs"
    )

    args = parser.parse_args(argv)

    clean_csv = args.clean_csv or resolve_file("carrier_ran_kpi_clean.csv")
    if not os.path.exists(clean_csv):
        clean_csv = args.clean_csv or resolve_file("carrier_kpi_clean.csv")
    forecast_csv = args.forecast_csv or resolve_file("carrier_kpi_forecast_2026_2027.csv")
    metrics_json = args.metrics_json or resolve_file("model_metrics.json")

    for fpath in [clean_csv, forecast_csv, metrics_json]:
        if not os.path.exists(fpath):
            print(f"[!] Critical data artifact missing: {fpath}", file=sys.stderr)
            sys.exit(1)

    # Full batch generation
    if args.carrier is None and args.kpi is None:
        generate_all_plots(
            output_dir=args.output_dir,
            artifacts_dir=args.artifacts_dir,
            dpi=args.dpi,
            clean_csv_path=clean_csv,
            forecast_csv_path=forecast_csv,
            metrics_json_path=metrics_json,
            quiet=args.quiet
        )
    else:
        hist_df = pd.read_csv(clean_csv)
        hist_df['date'] = pd.to_datetime(hist_df['date'])
        fc_df = pd.read_csv(forecast_csv)
        fc_df['date'] = pd.to_datetime(fc_df['date'])
        with open(metrics_json, 'r', encoding='utf-8') as f:
            m_dict = json.load(f)

        target_carriers = [args.carrier] if args.carrier else CARRIER_BANDS
        target_kpis = [args.kpi] if args.kpi else KPI_KEYS

        # Save decoupled single plots into artifacts/plots/individual
        indiv_base = os.path.join(args.artifacts_dir, "plots", "individual")
        for c in target_carriers:
            c_dir = os.path.join(indiv_base, f"carrier_{c}")
            os.makedirs(c_dir, exist_ok=True)
            for k in target_kpis:
                out_p = os.path.join(c_dir, f"{k}.png")
                plot_single_kpi(c, k, hist_df, fc_df, m_dict, out_path=out_p, dpi=args.dpi)
                print(f"[+] Saved standalone artifact: {out_p}")


if __name__ == "__main__":
    main()
