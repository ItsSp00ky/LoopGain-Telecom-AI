"""main.py: Master execution orchestrator for end-to-end KPI time-series prediction.
Executes:
1. Clean: Raw data normalization, date parsing, frequency validation, and anomaly treatment.
2. Split: Chronological Train / Validation / Test partitioning with zero leakage.
3. Train: Feature engineering, multi-model benchmarking, champion selection, and future forecasting.
4. Plot: High-resolution publication-quality visualization generation.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.clean import run_clean_pipeline
from src.split import run_split_pipeline
from src.features import prepare_datasets
from src.models import train_and_benchmark, retrain_champion, forecast_future
from src.plots import run_all_plots
import numpy as np


def main():
    print("*" * 70)
    print(" TELECOM NETWORK KPI PREDICTION PIPELINE")
    print(" Target: 4G Overall Accumulated Data Volume (GB)")
    print("*" * 70)

    # 1. Clean
    clean_df = run_clean_pipeline(
        raw_path="Year.csv",
        out_paths=["data/traffic_kpi_clean.csv"],
    )

    # 2. Split
    train_df, val_df, test_df = run_split_pipeline(input_csv="data/traffic_kpi_clean.csv")

    # 3. Features & Datasets
    datasets, scaler, feature_cols = prepare_datasets(clean_csv="data/traffic_kpi_clean.csv")

    # 4. Train & Benchmark
    results, metrics_df, champion_name = train_and_benchmark(datasets, feature_cols)

    # 5. Champion Retrain & Multi-step Forecast
    champion_model, test_pred, final_metrics = retrain_champion(
        datasets, feature_cols, champion_name
    )

    test_y = datasets["test"]["y"]
    res_std = float(np.std(test_y - test_pred))
    forecast_df = forecast_future(
        champion_model, datasets["full_df"], feature_cols, horizon_days=30, residual_std=res_std
    )
    forecast_path = Path("data/future_30d_forecast.csv")
    forecast_df.to_csv(forecast_path, index=False)
    print(f"Exported future forecast to: {forecast_path.resolve()}")

    # 6. Generate All Visual Plots
    generated_plots = run_all_plots(
        datasets=datasets,
        results=results,
        metrics_df=metrics_df,
        champion_name=champion_name,
        champion_model=champion_model,
        feature_cols=feature_cols,
    )

    print("*" * 70)
    print(" PIPELINE EXECUTION COMPLETED SUCCESSFULLY!")
    print(f" Champion Model: {champion_name}")
    print(f" Test WAPE:      {final_metrics['WAPE (%)']:.2f}%")
    print(f" Test MAE:       {final_metrics['MAE']:,.1f} GB")
    print(f" Test RMSE:      {final_metrics['RMSE']:,.1f} GB")
    print(f" Visual Plots:   {len(generated_plots)} figures generated in plots/")
    print("*" * 70)


if __name__ == "__main__":
    main()
