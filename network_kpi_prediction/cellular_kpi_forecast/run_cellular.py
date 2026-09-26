"""
main.py
Unified Command-Line Interface for KPI Prediction Pipeline.
Supports: split, train, plot, predict, and test workflows.
"""

import os
import sys
import argparse

_REPO_ROOT = os.path.abspath(os.path.dirname(__file__))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.kpi_config import CARRIER_BANDS, KPI_KEYS


def run_split():
    print("[*] Running Stage 1: Chronological Dataset Splitter (split.py)...")
    from run_split import main as split_main
    split_main()


def run_train():
    print("[*] Running Stage 2: Model Training & Forecasting Engine (train.py)...")
    import train_models
    train_models.run_pipeline()


def run_plot(carrier=None, kpi=None, dpi=300):
    print("[*] Running Stage 3: Publication Plot Generator (plot.py)...")
    from src.visualization import generate_all_plots, plot_single_kpi
    from generate_plots import resolve_file
    import json
    import pandas as pd

    clean_csv = resolve_file("carrier_ran_kpi_clean.csv")
    forecast_csv = resolve_file("carrier_kpi_forecast_2026_2027.csv")
    metrics_json = resolve_file("model_metrics.json")

    if carrier is None and kpi is None:
        generate_all_plots(dpi=dpi, clean_csv_path=clean_csv, forecast_csv_path=forecast_csv, metrics_json_path=metrics_json)
    else:
        hist_df = pd.read_csv(clean_csv)
        hist_df['date'] = pd.to_datetime(hist_df['date'])
        fc_df = pd.read_csv(forecast_csv)
        fc_df['date'] = pd.to_datetime(fc_df['date'])
        with open(metrics_json, 'r', encoding='utf-8') as f:
            m_dict = json.load(f)

        target_carriers = [carrier] if carrier else CARRIER_BANDS
        target_kpis = [kpi] if kpi else KPI_KEYS
        for c in target_carriers:
            c_dir = os.path.join(_REPO_ROOT, "plots", f"carrier_{c}")
            os.makedirs(c_dir, exist_ok=True)
            for k in target_kpis:
                out_p = os.path.join(c_dir, f"{k}.png")
                plot_single_kpi(c, k, hist_df, fc_df, m_dict, out_path=out_p, dpi=dpi)
                print(f"[+] Saved: {out_p}")


def run_predict(carrier: int, kpi: str, days: int = 7, live: bool = False):
    from predict import query_predictions
    query_predictions(carrier=carrier, kpi=kpi, days=days, force_live=live)


def run_tests() -> int:
    print("[*] Running Automated Test Suite across all 3GPP modules...")
    import unittest
    loader = unittest.TestLoader()
    suite = loader.discover(os.path.join(_REPO_ROOT, "tests"))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="3GPP Rel-17 Cellular KPI Prediction Pipeline")
    subparsers = parser.add_subparsers(dest="command", help="Workflow stage to execute")

    # split (Stage 1)
    subparsers.add_parser("split", help="Stage 1: Chronologically split telemetry into train/val/test")

    # train (Stage 2)
    subparsers.add_parser("train", help="Stage 2: Train models, select champions, and generate 365-day forecasts")

    # plot (Stage 3)
    plot_p = subparsers.add_parser("plot", aliases=["plots"], help="Stage 3: Generate 300-DPI publication-grade plots")
    plot_p.add_argument("--carrier", type=int, choices=CARRIER_BANDS, default=None, help="Filter by carrier band")
    plot_p.add_argument("--kpi", type=str, choices=KPI_KEYS, default=None, help="Filter by KPI key")
    plot_p.add_argument("--dpi", type=int, default=300, help="Plot resolution (default: 300)")

    # predict
    pred_p = subparsers.add_parser("predict", help="Query point predictions and 90% confidence ribbons")
    pred_p.add_argument("--carrier", type=int, required=True, choices=CARRIER_BANDS, help="Carrier band (e.g. 3500)")
    pred_p.add_argument("--kpi", type=str, required=True, choices=KPI_KEYS, help="KPI key (e.g. dl_throughput_mbps)")
    pred_p.add_argument("--days", type=int, default=7, help="Number of days to forecast (default: 7)")
    pred_p.add_argument("--live", action="store_true", help="Force live model bundle inference")

    # test
    subparsers.add_parser("test", help="Execute all unit tests across config, clean, split, features, models, plots, export")

    args = parser.parse_args(argv)

    if args.command == "split":
        run_split()
        return 0
    elif args.command == "train":
        run_train()
        return 0
    elif args.command in ["plot", "plots"]:
        run_plot(carrier=args.carrier, kpi=args.kpi, dpi=args.dpi)
        return 0
    elif args.command == "predict":
        run_predict(carrier=args.carrier, kpi=args.kpi, days=args.days, live=args.live)
        return 0
    elif args.command == "test":
        return run_tests()
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
