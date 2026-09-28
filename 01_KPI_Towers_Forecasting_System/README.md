# 📡 4G LTE Cell Tower Operational KPI Forecasting System

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![XGBoost](https://img.shields.io/badge/XGBoost-2.0%2B-orange.svg)](https://xgboost.ai/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](#)

> Production-ready machine learning forecasting architecture for cellular telecommunications networks. Predicts core operational KPIs across **1,067 4G LTE cell towers** in Libya using gradient-boosted decision trees with leak-free temporal feature engineering.

---

## 🌟 Key Highlights

* **Hierarchical Forecasting**: Accurately forecasts both individual tower-level dynamics ($R^2 = 0.9017$) and countrywide aggregate demand (**1.38% MAPE**).
* **Zero Temporal Leakage**: Evaluated on a strict **70% chronological train (254 days) / 30% out-of-time test horizon (109 days)**.
* **4 Operational Pillars**:
  * `Avg RRC Connected users` (Traffic Load & Capacity)
  * `E-UTRAN IP Throughput UE DL` (Downlink Speed & QoE)
  * `4G Cell Av. (%)` (Site Uptime & Outage Risk)
  * `E-RAB Drop Rate` (Session Retention & Drop Stability)

---

## 📁 Repository Structure

```
01_KPI_Forecasting_System/
│
├── README.md                      # Project overview & quickstart
├── MODEL_ARCHITECTURE.md          # In-depth mathematical formulation & ML specs
├── RESULTS_AND_EVALUATION.md      # Performance benchmarks, metrics & plots
├── requirements.txt               # Dependencies
├── .gitignore                     # Git ignore rules
│
├── data/                          # Cleaned dataset & tower mapping
│   ├── Data_Cleaned.csv           # 378,631 rows, 0 NaNs, ISO dates
│   └── tower_mapping.csv          # Anonymization lookup table
│
├── src/                           # Modular production source code
│   ├── data_loader.py             # Data loading and 70/30 chronological split
│   ├── feature_engineering.py     # Lags, rolling stats, cyclical calendar encodings
│   └── train_and_evaluate.py      # End-to-end training and inference CLI
│
├── models/                        # Saved Model Checkpoints ("save the training")
│   ├── xgb_connected_users.joblib / .json
│   ├── xgb_dl_throughput.joblib / .json
│   ├── xgb_cell_availability.joblib / .json
│   ├── xgb_drop_rate.joblib / .json
│   └── feature_importance.csv
│
├── forecasts/                     # Out-of-Time Test Predictions
│   ├── tower_level_forecast_predictions.csv  # 114,233 test rows with actual vs predicted
│   └── model_evaluation_metrics.json         # Performance summary JSON
│
└── assets/                        # High-resolution visual forecast plots
    ├── forecast_connected_users.png
    ├── forecast_dl_throughput.png
    ├── forecast_cell_availability.png
    ├── forecast_drop_rate.png
    ├── visual_micro_tower_forecasts.png
    └── visual_feature_importance.png
```

---

## 🚀 Quickstart & Installation

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/your-username/4g-lte-kpi-forecasting.git
cd 4g-lte-kpi-forecasting
pip install -r requirements.txt
```

### 2. Train Models & Generate Forecasts
```bash
python src/train_and_evaluate.py
```

### 3. Load Model in Python
```python
import joblib
import pandas as pd

# Load the trained Connected Users model
model = joblib.load("models/xgb_connected_users.joblib")

# Load out-of-time test predictions
predictions = pd.read_csv("forecasts/tower_level_forecast_predictions.csv")
print(predictions.head())
```

---

## 📊 Summary Performance Benchmarks

| Target KPI | Site-Level $R^2$ | Site MAE | Network Aggregate Metric | Network MAPE |
| :--- | :---: | :---: | :--- | :---: |
| **Connected Users** | **0.9017** | 1.357 users | Total Network Users | **1.38%** |
| **DL Throughput (Mbps)**| **0.8663** | 1.341 Mbps | Mean Network Speed | **4.72%** |
| **Cell Availability (%)**| 0.3866 | 6.247 % | Mean Network Uptime | **4.51%** |
| **Drop Rate (%)** | 0.3905 | **0.071 %** | Mean Network Drop Rate | **8.28%** |

For comprehensive mathematical equations, feature formulations, and visual charts, consult:
* 📄 [MODEL_ARCHITECTURE.md](MODEL_ARCHITECTURE.md)
* 📊 [RESULTS_AND_EVALUATION.md](RESULTS_AND_EVALUATION.md)
