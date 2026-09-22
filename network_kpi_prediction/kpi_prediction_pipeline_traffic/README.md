# Telecom Traffic KPI Prediction Pipeline (`kpi_prediction_pipeline_traffic`)

End-to-end time-series forecasting pipeline for **4G Overall Accumulated Data Volume (GB)**.

## Project Structure

```
kpi_prediction_pipeline_traffic/
├── Year.csv                      # Raw input dataset (264 daily entries)
├── main.py                       # Master orchestrator script (Clean -> Split -> Train -> Plot)
├── README.md                     # Project overview and run instructions
├── src/
│   ├── __init__.py
│   ├── clean.py                  # Header formatting, date parsing, frequency validation & anomaly imputation
│   ├── split.py                  # Chronological Train (70%) / Val (15%) / Test (15%) partitioning
│   ├── features.py               # 28 engineered lag, rolling window, and cyclical calendar features
│   ├── models.py                 # Multi-model benchmarking (Naive, Ridge, RF, XGBoost) & 30-day forecast
│   └── plots.py                  # High-resolution 300-DPI publication-grade visualization suite
├── data/
│   ├── traffic_kpi_clean.csv     # Cleaned, validated, and anomaly-imputed 4G traffic dataset
│   ├── train.csv                 # Chronological training partition (Jan 29 - Jul 12)
│   ├── val.csv                   # Validation partition (Jul 13 - Aug 16)
│   ├── test.csv                  # Holdout test partition (Aug 17 - Sep 21)
│   └── future_30d_forecast.csv   # 30-day recursive forecast with 80% and 95% confidence intervals
└── plots/
    ├── 01_eda_and_anomalies.png          # Historical trajectory & detected outages/anomalies
    ├── 02_chronological_splits.png       # Strict zero-leakage timeline partitions
    ├── 03_model_benchmark_metrics.png   # WAPE (%) and MAE comparison across models
    ├── 04_actual_vs_predicted_test.png   # Holdout actuals vs predictions and residuals
    ├── 05_feature_importance.png         # Top predictive drivers for the champion model
    └── 06_future_30d_forecast.png        # 30-day forecast cone with capacity threshold
```

## Quick Start

Execute the complete pipeline end-to-end:
```powershell
cd kpi_prediction_pipeline
python main.py
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
