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


def run_split(data_path=None, output_dir=None, train_ratio=0.70, val_ratio=0.15, test_ratio=0.15):
    print("[*] Running Stage 1: Chronological Dataset Splitter (split.py)...")
    from run_split import main as split_main
    args = []
    if data_path:
        args.extend(["--data-path", data_path])
    if output_dir:
        args.extend(["--output-dir", output_dir])
    args.extend(["--train-ratio", str(train_ratio), "--val-ratio", str(val_ratio), "--test-ratio", str(test_ratio)])
    split_main(args)


def run_train(
    data_path=None, output_dir=None, models_dir=None, splits_dir=None,
    train_ratio=None, val_ratio=None, test_ratio=None, horizon_days=None,
    carrier=None, kpi=None
):
    print("[*] Running Stage 2: Model Training & Forecasting Engine (train.py)...")
    import train_models
    carriers = [carrier] if carrier else None
    kpis = [kpi] if kpi else None
    train_models.run_pipeline(
        data_path=data_path,
        output_dir=output_dir,
        models_dir=models_dir,
        splits_dir=splits_dir,
        train_ratio=train_ratio,
        val_ratio=val_ratio,
        test_ratio=test_ratio,
        horizon_days=horizon_days,
        target_carriers=carriers,
        target_kpis=kpis
    )


def run_plot(carrier=None, kpi=None, dpi=300, output_dir=None):
    print("[*] Running Stage 3: Publication Plot Generator (plot.py)...")
    from src.visualization import generate_all_plots, plot_single_kpi
    from generate_plots import resolve_file
    import json
    import pandas as pd

    if output_dir is None:
        output_dir = os.path.join(_REPO_ROOT, "plots")

    clean_csv = resolve_file("carrier_ran_kpi_clean.csv")
    forecast_csv = resolve_file("carrier_kpi_forecast_2026_2027.csv")
    metrics_json = resolve_file("model_metrics.json")

    if carrier is None and kpi is None:
        generate_all_plots(output_dir=output_dir, dpi=dpi, clean_csv_path=clean_csv, forecast_csv_path=forecast_csv, metrics_json_path=metrics_json)
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
            c_dir = os.path.join(output_dir, f"carrier_{c}")
            os.makedirs(c_dir, exist_ok=True)
            for k in target_kpis:
                out_p = os.path.join(c_dir, f"{k}.png")
                plot_single_kpi(c, k, hist_df, fc_df, m_dict, out_path=out_p, dpi=dpi)
                print(f"[+] Saved: {out_p}")


def run_predict(carrier: int, kpi: str, days: int = 7, live: bool = False):
    from run_inference import query_predictions
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
    split_p = subparsers.add_parser("split", help="Stage 1: Chronologically split telemetry into train/val/test")
    split_p.add_argument("--data-path", type=str, default=None, help="Path to clean telemetry CSV")
    split_p.add_argument("--output-dir", type=str, default=None, help="Output directory for split datasets")
    split_p.add_argument("--train-ratio", type=float, default=0.70, help="Train ratio (default: 0.70)")
    split_p.add_argument("--val-ratio", type=float, default=0.15, help="Val ratio (default: 0.15)")
    split_p.add_argument("--test-ratio", type=float, default=0.15, help="Test ratio (default: 0.15)")

    # train (Stage 2)
    train_p = subparsers.add_parser("train", help="Stage 2: Train models, select champions, and generate forecasts")
    train_p.add_argument("--data-path", type=str, default=None, help="Path to clean telemetry CSV")
    train_p.add_argument("--output-dir", type=str, default=None, help="Output directory for metrics and forecasts")
    train_p.add_argument("--models-dir", type=str, default=None, help="Directory to save serialized models")
    train_p.add_argument("--splits-dir", type=str, default=None, help="Directory to save dataset splits")
    train_p.add_argument("--train-ratio", type=float, default=None, help="Train ratio (default: 0.70)")
    train_p.add_argument("--val-ratio", type=float, default=None, help="Val ratio (default: 0.15)")
    train_p.add_argument("--test-ratio", type=float, default=None, help="Test ratio (default: 0.15)")
    train_p.add_argument("--horizon-days", type=int, default=None, help="Forward forecast horizon in days (default: 365)")
    train_p.add_argument("--carrier", "--target-carriers", type=int, choices=CARRIER_BANDS, default=None, dest="carrier", help="Filter by carrier band")
    train_p.add_argument("--kpi", "--target-kpis", type=str, choices=KPI_KEYS, default=None, dest="kpi", help="Filter by KPI key")

    # plot (Stage 3)
    plot_p = subparsers.add_parser("plot", aliases=["plots"], help="Stage 3: Generate 300-DPI publication-grade plots")
    plot_p.add_argument("--carrier", type=int, choices=CARRIER_BANDS, default=None, help="Filter by carrier band")
    plot_p.add_argument("--kpi", type=str, choices=KPI_KEYS, default=None, help="Filter by KPI key")
    plot_p.add_argument("--dpi", type=int, default=300, help="Plot resolution (default: 300)")
    plot_p.add_argument("--output-dir", type=str, default=None, help="Directory to save generated plots")

    # predict
    pred_p = subparsers.add_parser("predict", help="Query point predictions and 90%% confidence ribbons")
    pred_p.add_argument("--carrier", type=int, required=True, choices=CARRIER_BANDS, help="Carrier band (e.g. 3500)")
    pred_p.add_argument("--kpi", type=str, required=True, choices=KPI_KEYS, help="KPI key (e.g. dl_throughput_mbps)")
    pred_p.add_argument("--days", type=int, default=7, help="Number of days to forecast (default: 7)")
    pred_p.add_argument("--live", action="store_true", help="Force live model bundle inference")

    # test
    subparsers.add_parser("test", help="Execute all unit tests across config, clean, split, features, models, plots, export")

    args = parser.parse_args(argv)

    if args.command == "split":
        run_split(
            data_path=args.data_path,
            output_dir=args.output_dir,
            train_ratio=args.train_ratio,
            val_ratio=args.val_ratio,
            test_ratio=args.test_ratio
        )
        return 0
    elif args.command == "train":
        run_train(
            data_path=args.data_path,
            output_dir=args.output_dir,
            models_dir=args.models_dir,
            splits_dir=args.splits_dir,
            train_ratio=args.train_ratio,
            val_ratio=args.val_ratio,
            test_ratio=args.test_ratio,
            horizon_days=args.horizon_days,
            carrier=args.carrier,
            kpi=args.kpi
        )
        return 0
    elif args.command in ["plot", "plots"]:
        run_plot(carrier=args.carrier, kpi=args.kpi, dpi=args.dpi, output_dir=args.output_dir)
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
