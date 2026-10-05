# Telecom Traffic KPI Prediction Pipeline (`traffic_volume_forecast`)

End-to-end time-series forecasting pipeline for **4G Overall Accumulated Data Volume (GB)**.

## Project Structure

```
traffic_volume_forecast/
├── 4g_traffic_volume_daily.csv                      # Raw input dataset (264 daily entries)
├── run_traffic.py                       # Master orchestrator script (Clean -> Split -> Train -> Plot)
├── README.md                     # Project overview and run instructions
├── src/
│   ├── __init__.py
│   ├── data_cleaning.py                  # Header formatting, date parsing, frequency validation & anomaly imputation
│   ├── temporal_splitting.py                  # Chronological Train (70%) / Val (15%) / Test (15%) partitioning
│   ├── feature_engineering.py               # 28 engineered lag, rolling window, and cyclical calendar features
│   ├── model_definitions.py                 # Multi-model benchmarking (Naive, Ridge, RF, XGBoost) & 30-day forecast
│   └── visualization.py                  # High-resolution 300-DPI publication-grade visualization suite
├── data/
│   ├── traffic_kpi_clean.csv     # Cleaned, validated, and anomaly-imputed 4G traffic dataset
│   ├── train.csv                 # Chronological training partition (Jan 29 - Jul 12)
│   ├── val.csv                   # Validation partition (Jul 13 - Aug 16)
│   ├── test.csv                  # Holdout test partition (Aug 17 - Sep 21)
│   └── future_30d_forecast.csv   # 30-day recursive forecast with 80% and 95% confidence intervals
└── plots/
    ├── traffic_diagnostic_overview.png   # Consolidated 3-panel publication diagnostic (Anomalies, Splits, Holdout vs Naive)
    ├── 03_model_benchmark_metrics.png   # WAPE (%) and MAE comparison across models
    ├── 04_actual_vs_predicted_test.png   # Holdout actuals vs predictions and residuals
    ├── 05_feature_importance.png         # Top predictive drivers for the champion model
    ├── 06_future_30d_forecast.png        # 30-day forecast cone with capacity threshold
    └── 07_multivariate_vs_univariate_comparison.png # Exogenous feature ablation study
```

## Quick Start

Execute the complete pipeline end-to-end:
```powershell
cd traffic_volume_forecast
python run_traffic.py
```

Or execute modular steps individually:
```powershell
python -m src.clean     # Step 1: Clean raw data and impute transient anomalies
python -m src.split     # Step 2: Chronologically partition datasets
python -m src.features  # Step 3: Engineer 28 time-series features
python -m src.models    # Step 4: Benchmark models and generate 30-day forecast
python -m src.plots     # Step 5: Render all 6 visualization charts
```

## Benchmark Summary

| Model | Val WAPE (%) | Test WAPE (%) | Test MAE (GB) | Test $R^2$ |
| :--- | :---: | :---: | :---: | :---: |
| **Random Forest (Champion)** | **2.20%** | **1.97%** | **20,489.3** | **0.608** |
| **XGBoost Regressor** | 2.38% | 2.17% | 22,651.3 | 0.485 |
| **Ridge Regression** | 2.52% | 2.20% | 22,961.2 | 0.620 |
| **Seasonal Naive ($t-7$)** | 3.52% | 3.16% | 32,941.2 | 0.242 |
