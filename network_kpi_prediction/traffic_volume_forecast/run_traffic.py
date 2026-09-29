"""run_traffic.py: Master execution orchestrator for 4G macro network traffic volume prediction.
Supports modular subcommands (clean, split, train, plot, test, all) with dynamic path resolution
and customizable hyperparameters, splitting ratios, and forecast horizons.
"""

import sys
import argparse
from pathlib import Path
import pandas as pd
import numpy as np

# Ensure project package root is in sys.path
_PKG_ROOT = Path(__file__).resolve().parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from src.data_cleaning import run_clean_pipeline, resolve_raw_traffic_file
from src.temporal_splitting import run_split_pipeline, resolve_clean_traffic_file
from src.feature_engineering import prepare_datasets, prepare_multivariate_datasets
from src.model_definitions import train_and_benchmark, retrain_champion, forecast_future
from src.visualization import run_all_plots, plot_multivariate_vs_univariate_comparison


def run_clean_stage(raw_path=None, output_dir=None, z_threshold=3.0):
    out_dir = Path(output_dir) if output_dir else _PKG_ROOT / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    clean_csv_path = out_dir / "traffic_kpi_clean.csv"
    return run_clean_pipeline(
        raw_path=raw_path,
        out_paths=[clean_csv_path],
        z_threshold=z_threshold,
    )


def run_split_stage(input_csv=None, output_dir=None, train_ratio=0.70, val_ratio=0.15):
    out_dir = Path(output_dir) if output_dir else _PKG_ROOT / "data"
    splits_dir = out_dir / "splits"
    return run_split_pipeline(
        input_csv=input_csv,
        train_ratio=train_ratio,
        val_ratio=val_ratio,
        save_dir=splits_dir,
    )


def run_train_stage(
    clean_csv=None,
    output_dir=None,
    train_ratio=0.70,
    val_ratio=0.15,
    horizon_days=30,
):
    out_dir = Path(output_dir) if output_dir else _PKG_ROOT / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    datasets, scaler, feature_cols = prepare_datasets(
        clean_csv=clean_csv,
        train_ratio=train_ratio,
        val_ratio=val_ratio,
    )

    results, metrics_df, champion_name = train_and_benchmark(datasets, feature_cols)
    champion_model, test_pred, final_metrics = retrain_champion(
        datasets, feature_cols, champion_name
    )

    test_y = datasets["test"]["y"]
    res_std = float(np.std(test_y - test_pred))
    forecast_df = forecast_future(
        champion_model,
        datasets["full_df"],
        feature_cols,
        horizon_days=horizon_days,
        residual_std=res_std,
    )

    forecast_path = out_dir / f"future_{horizon_days}d_forecast.csv"
    forecast_df.to_csv(forecast_path, index=False)
    # Also save standard future_30d_forecast.csv for compatibility if horizon is 30
    if horizon_days == 30:
        forecast_df.to_csv(out_dir / "future_30d_forecast.csv", index=False)

    print(f"Exported future forecast to: {forecast_path.resolve()}")

    return {
        "datasets": datasets,
        "results": results,
        "metrics_df": metrics_df,
        "champion_name": champion_name,
        "champion_model": champion_model,
        "feature_cols": feature_cols,
        "final_metrics": final_metrics,
        "forecast_path": forecast_path,
        "forecast_df": forecast_df,
    }


def run_enriched_stage(
    clean_csv=None,
    macro_csv=None,
    carrier_csv=None,
    output_dir=None,
    train_ratio=0.70,
    val_ratio=0.15,
    horizon_days=30,
):
    """Same shape as `run_train_stage`, but trains and forecasts with every exogenous
    network KPI this module has (see `prepare_multivariate_datasets`), not just the
    traffic series' own history."""
    out_dir = Path(output_dir) if output_dir else _PKG_ROOT / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    datasets, scaler, feature_cols = prepare_multivariate_datasets(
        clean_csv=clean_csv,
        macro_csv=macro_csv,
        carrier_csv=carrier_csv,
        train_ratio=train_ratio,
        val_ratio=val_ratio,
    )

    results, metrics_df, champion_name = train_and_benchmark(datasets, feature_cols)
    champion_model, test_pred, final_metrics = retrain_champion(
        datasets, feature_cols, champion_name
    )

    test_y = datasets["test"]["y"]
    res_std = float(np.std(test_y - test_pred))
    forecast_df = forecast_future(
        champion_model,
        datasets["full_df"],
        feature_cols,
        horizon_days=horizon_days,
        residual_std=res_std,
        exo_cols=datasets["exo_cols"],
    )

    forecast_path = out_dir / f"future_{horizon_days}d_enriched_forecast.csv"
    forecast_df.to_csv(forecast_path, index=False)
    print(f"Exported enriched future forecast to: {forecast_path.resolve()}")

    return {
        "datasets": datasets,
        "results": results,
        "metrics_df": metrics_df,
        "champion_name": champion_name,
        "champion_model": champion_model,
        "feature_cols": feature_cols,
        "final_metrics": final_metrics,
        "forecast_path": forecast_path,
        "forecast_df": forecast_df,
        "exo_cols": datasets["exo_cols"],
    }


def run_multivariate_stage(
    clean_csv=None,
    macro_csv=None,
    output_dir=None,
    train_ratio=0.70,
    val_ratio=0.15,
):
    out_dir = Path(output_dir) if output_dir else _PKG_ROOT / "data"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("MULTIVARIATE 4G TRAFFIC FORECASTING // EXOGENOUS RADIO NETWORK INTEGRATION")
    print("Datasets: 4g_traffic_volume_daily.csv + macro_network_kpis_daily.csv")
    print("=" * 80)

    # 1. Prepare univariate baseline datasets
    print("\n[1/3] Benchmarking Univariate Baseline (Past Volume Lags Only)...")
    uni_datasets, _, uni_features = prepare_datasets(
        clean_csv=clean_csv, train_ratio=train_ratio, val_ratio=val_ratio
    )
    uni_results, uni_metrics_df, uni_champ = train_and_benchmark(uni_datasets, uni_features)
    _, _, uni_final_metrics = retrain_champion(uni_datasets, uni_features, uni_champ)

    # 2. Prepare multivariate datasets with shifted radio KPIs
    print("\n[2/3] Benchmarking Multivariate Exogenous Model (Volume Lags + Shifted Radio KPIs)...")
    multi_datasets, _, multi_features = prepare_multivariate_datasets(
        clean_csv=clean_csv, macro_csv=macro_csv, train_ratio=train_ratio, val_ratio=val_ratio
    )
    multi_results, multi_metrics_df, multi_champ = train_and_benchmark(multi_datasets, multi_features)
    _, _, multi_final_metrics = retrain_champion(multi_datasets, multi_features, multi_champ)

    # 3. Comparative Benchmarking
    print("\n[3/3] Generating Univariate vs Multivariate Performance Comparison...")
    comp_df = pd.DataFrame([
        {
            "Model Architecture": f"Univariate Champion ({uni_champ})",
            "Features": len(uni_features),
            "Test-MAE": round(uni_final_metrics["MAE"], 2),
            "Test-RMSE": round(uni_final_metrics["RMSE"], 2),
            "Test-WAPE (%)": round(uni_final_metrics["WAPE (%)"], 2),
            "Test-R2": round(uni_final_metrics["R2"], 4),
        },
        {
            "Model Architecture": f"Multivariate Champion ({multi_champ})",
            "Features": len(multi_features),
            "Test-MAE": round(multi_final_metrics["MAE"], 2),
            "Test-RMSE": round(multi_final_metrics["RMSE"], 2),
            "Test-WAPE (%)": round(multi_final_metrics["WAPE (%)"], 2),
            "Test-R2": round(multi_final_metrics["R2"], 4),
        }
    ])

    print("\n" + "=" * 80)
    print("UNIVARIATE VS. MULTIVARIATE PERFORMANCE COMPARISON:")
    print("=" * 80)
    print(comp_df.to_string(index=False))
    print("=" * 80 + "\n")

    comp_csv = out_dir / "multivariate_vs_univariate_comparison.csv"
    comp_df.to_csv(comp_csv, index=False)
    print(f"Comparison metrics exported to: {comp_csv.resolve()}")

    # Generate publication plot
    plot_multivariate_vs_univariate_comparison(comp_df, plots_dir=_PKG_ROOT / "plots")

    return {
        "comparison_df": comp_df,
        "univariate_champion": uni_champ,
        "multivariate_champion": multi_champ,
        "univariate_metrics": uni_final_metrics,
        "multivariate_metrics": multi_final_metrics,
    }


def run_plot_stage(
    datasets=None,
    results=None,
    metrics_df=None,
    champion_name=None,
    champion_model=None,
    feature_cols=None,
    clean_csv=None,
    forecast_csv=None,
    plots_dir=None,
):
    target_plots_dir = Path(plots_dir) if plots_dir else _PKG_ROOT / "plots"

    if datasets is None or results is None or champion_model is None:
        train_out = run_train_stage(clean_csv=clean_csv)
        datasets = train_out["datasets"]
        results = train_out["results"]
        metrics_df = train_out["metrics_df"]
        champion_name = train_out["champion_name"]
        champion_model = train_out["champion_model"]
        feature_cols = train_out["feature_cols"]
        forecast_csv = train_out["forecast_path"]

    return run_all_plots(
        datasets=datasets,
        results=results,
        metrics_df=metrics_df,
        champion_name=champion_name,
        champion_model=champion_model,
        feature_cols=feature_cols,
        clean_csv=clean_csv,
        forecast_csv=forecast_csv,
        plots_dir=target_plots_dir,
    )


def run_tests() -> int:
    print("[*] Running Automated Test Suite across all traffic volume modules...")
    import unittest
    loader = unittest.TestLoader()
    suite = loader.discover(str(_PKG_ROOT / "tests"))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def run_all_pipeline(
    raw_path=None,
    output_dir=None,
    plots_dir=None,
    train_ratio=0.70,
    val_ratio=0.15,
    horizon_days=30,
    z_threshold=3.0,
    skip_plots=False,
) -> int:
    print("*" * 70)
    print(" TELECOM NETWORK KPI PREDICTION PIPELINE")
    print(" Target: 4G Overall Accumulated Data Volume (GB)")
    print("*" * 70)

    out_dir = Path(output_dir) if output_dir else _PKG_ROOT / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    target_plots_dir = Path(plots_dir) if plots_dir else _PKG_ROOT / "plots"

    # 1. Clean
    clean_csv = out_dir / "traffic_kpi_clean.csv"
    run_clean_pipeline(
        raw_path=raw_path,
        out_paths=[clean_csv],
        z_threshold=z_threshold,
    )

    # 2. Split
    splits_dir = out_dir / "splits"
    run_split_pipeline(
        input_csv=clean_csv,
        train_ratio=train_ratio,
        val_ratio=val_ratio,
        save_dir=splits_dir,
    )

    # 3. Train & Benchmark
    train_out = run_train_stage(
        clean_csv=clean_csv,
        output_dir=out_dir,
        train_ratio=train_ratio,
        val_ratio=val_ratio,
        horizon_days=horizon_days,
    )

    # 4. Generate Visual Plots
    generated_plots = []
    if not skip_plots:
        generated_plots = run_plot_stage(
            datasets=train_out["datasets"],
            results=train_out["results"],
            metrics_df=train_out["metrics_df"],
            champion_name=train_out["champion_name"],
            champion_model=train_out["champion_model"],
            feature_cols=train_out["feature_cols"],
            clean_csv=clean_csv,
            forecast_csv=train_out["forecast_path"],
            plots_dir=target_plots_dir,
        )

    final_metrics = train_out["final_metrics"]
    champion_name = train_out["champion_name"]

    print("*" * 70)
    print(" PIPELINE EXECUTION COMPLETED SUCCESSFULLY!")
    print(f" Champion Model: {champion_name}")
    print(f" Test WAPE:      {final_metrics['WAPE (%)']:.2f}%")
    print(f" Test MAE:       {final_metrics['MAE']:,.1f} GB")
    print(f" Test RMSE:      {final_metrics['RMSE']:,.1f} GB")
    if generated_plots:
        print(f" Visual Plots:   {len(generated_plots)} figures generated in {target_plots_dir.resolve()}")
    print("*" * 70)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Master execution orchestrator for end-to-end 4G traffic volume prediction."
    )
    subparsers = parser.add_subparsers(dest="command", help="Workflow stage to execute")

    # all
    all_p = subparsers.add_parser("all", help="Execute complete end-to-end pipeline (clean -> split -> train -> plot)")
    all_p.add_argument("--data-path", "-d", type=str, default=None, help="Path to raw telemetry CSV")
    all_p.add_argument("--output-dir", "-o", type=str, default=None, help="Directory to save clean data and forecasts")
    all_p.add_argument("--plots-dir", "-p", type=str, default=None, help="Directory to save generated plots")
    all_p.add_argument("--horizon-days", "--horizon", type=int, default=30, help="Future forecast horizon in days (default: 30)")
    all_p.add_argument("--train-ratio", type=float, default=0.70, help="Train ratio (default: 0.70)")
    all_p.add_argument("--val-ratio", type=float, default=0.15, help="Val ratio (default: 0.15)")
    all_p.add_argument("--z-threshold", type=float, default=3.0, help="Anomaly detection z-threshold (default: 3.0)")
    all_p.add_argument("--skip-plots", action="store_true", help="Skip generating plot figures")

    # clean
    clean_p = subparsers.add_parser("clean", help="Stage 1: Clean and regularize raw 4G traffic data")
    clean_p.add_argument("--data-path", "-d", type=str, default=None, help="Path to raw traffic CSV")
    clean_p.add_argument("--output-dir", "-o", type=str, default=None, help="Output directory for clean CSV")
    clean_p.add_argument("--z-threshold", type=float, default=3.0, help="Anomaly detection z-threshold (default: 3.0)")

    # split
    split_p = subparsers.add_parser("split", help="Stage 2: Chronologically partition data (Train/Val/Test)")
    split_p.add_argument("--data-path", "-d", type=str, default=None, help="Path to clean traffic CSV")
    split_p.add_argument("--output-dir", "-o", type=str, default=None, help="Output directory for split partitions")
    split_p.add_argument("--train-ratio", type=float, default=0.70, help="Train ratio (default: 0.70)")
    split_p.add_argument("--val-ratio", type=float, default=0.15, help="Val ratio (default: 0.15)")

    # train
    train_p = subparsers.add_parser("train", help="Stage 3: Train models, benchmark champions, and generate forecasts")
    train_p.add_argument("--data-path", "-d", type=str, default=None, help="Path to clean traffic CSV")
    train_p.add_argument("--output-dir", "-o", type=str, default=None, help="Output directory for forecasts and models")
    train_p.add_argument("--train-ratio", type=float, default=0.70, help="Train ratio (default: 0.70)")
    train_p.add_argument("--val-ratio", type=float, default=0.15, help="Val ratio (default: 0.15)")
    train_p.add_argument("--horizon-days", "--horizon", type=int, default=30, help="Future forecast horizon in days (default: 30)")

    # plot
    plot_p = subparsers.add_parser("plot", aliases=["plots"], help="Stage 4: Generate publication-grade plots")
    plot_p.add_argument("--clean-csv", type=str, default=None, help="Path to clean historical CSV")
    plot_p.add_argument("--forecast-csv", type=str, default=None, help="Path to forecast CSV")
    plot_p.add_argument("--plots-dir", "-p", type=str, default=None, help="Directory to save plots")

    # multivariate
    multi_p = subparsers.add_parser("multivariate", aliases=["multi"], help="Benchmark multivariate exogenous radio KPIs against univariate baseline")
    multi_p.add_argument("--data-path", "-d", type=str, default=None, help="Path to clean traffic CSV")
    multi_p.add_argument("--macro-path", "-m", type=str, default=None, help="Path to macro radio KPIs CSV")
    multi_p.add_argument("--output-dir", "-o", type=str, default=None, help="Output directory")
    multi_p.add_argument("--train-ratio", type=float, default=0.70, help="Train ratio (default: 0.70)")
    multi_p.add_argument("--val-ratio", type=float, default=0.15, help="Val ratio (default: 0.15)")

    # enriched
    enriched_p = subparsers.add_parser("enriched", help="Train and forecast with every exogenous network KPI this module has")
    enriched_p.add_argument("--data-path", "-d", type=str, default=None, help="Path to clean traffic CSV")
    enriched_p.add_argument("--macro-path", "-m", type=str, default=None, help="Path to macro radio KPIs CSV")
    enriched_p.add_argument("--carrier-path", "-c", type=str, default=None, help="Path to per-band carrier KPIs CSV")
    enriched_p.add_argument("--output-dir", "-o", type=str, default=None, help="Output directory")
    enriched_p.add_argument("--train-ratio", type=float, default=0.70, help="Train ratio (default: 0.70)")
    enriched_p.add_argument("--val-ratio", type=float, default=0.15, help="Val ratio (default: 0.15)")
    enriched_p.add_argument("--horizon-days", "--horizon", type=int, default=30, help="Future forecast horizon in days (default: 30)")

    # test
    subparsers.add_parser("test", help="Execute all unit tests for the traffic volume prediction pipeline")

    # If no arguments provided, default to 'all'
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        return run_all_pipeline()

    args = parser.parse_args(argv)

    if args.command in [None, "all"]:
        return run_all_pipeline(
            raw_path=getattr(args, "data_path", None),
            output_dir=getattr(args, "output_dir", None),
            plots_dir=getattr(args, "plots_dir", None),
            train_ratio=getattr(args, "train_ratio", 0.70),
            val_ratio=getattr(args, "val_ratio", 0.15),
            horizon_days=getattr(args, "horizon_days", 30),
            z_threshold=getattr(args, "z_threshold", 3.0),
            skip_plots=getattr(args, "skip_plots", False),
        )
    elif args.command == "clean":
        run_clean_stage(
            raw_path=args.data_path,
            output_dir=args.output_dir,
            z_threshold=args.z_threshold,
        )
        return 0
    elif args.command == "split":
        run_split_stage(
            input_csv=args.data_path,
            output_dir=args.output_dir,
            train_ratio=args.train_ratio,
            val_ratio=args.val_ratio,
        )
        return 0
    elif args.command == "train":
        run_train_stage(
            clean_csv=args.data_path,
            output_dir=args.output_dir,
            train_ratio=args.train_ratio,
            val_ratio=args.val_ratio,
            horizon_days=args.horizon_days,
        )
        return 0
    elif args.command in ["plot", "plots"]:
        run_plot_stage(
            clean_csv=args.clean_csv,
            forecast_csv=args.forecast_csv,
            plots_dir=args.plots_dir,
        )
        return 0
    elif args.command in ["multivariate", "multi"]:
        res = run_multivariate_stage(
            clean_csv=getattr(args, "data_path", None),
            macro_csv=getattr(args, "macro_path", None),
            output_dir=getattr(args, "output_dir", None),
            train_ratio=getattr(args, "train_ratio", 0.70),
            val_ratio=getattr(args, "val_ratio", 0.15),
        )
        return 0
    elif args.command == "enriched":
        run_enriched_stage(
            clean_csv=args.data_path,
            macro_csv=args.macro_path,
            carrier_csv=args.carrier_path,
            output_dir=args.output_dir,
            train_ratio=args.train_ratio,
            val_ratio=args.val_ratio,
            horizon_days=args.horizon_days,
        )
        return 0
    elif args.command == "test":
        return run_tests()
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
