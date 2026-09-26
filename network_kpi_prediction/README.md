# Network KPI & Traffic Prediction Engine
### Loop Gain – AI Telecom Suite // Samsung Innovation Campus (SIC) Capstone Project

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![Domain](https://img.shields.io/badge/Domain-3GPP_Rel--17_NWDAF-orange.svg)](#)
[![Tests](https://img.shields.io/badge/Tests-48%20Passed%20(100%25)-brightgreen.svg)](#)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](#)

An enterprise-grade telecommunications analytics and time-series forecasting subsystem engineered by **Maher Alqadhi** as part of **Team Loop Gain**. Built in accordance with **3GPP Rel-17 NWDAF (TS 28.552 / TS 29.520)** and **O-RAN Near-RT RIC A1 Policy** specifications.

---

## 🎯 System Objectives

1. **Cellular Multi-Band Telemetry Forecasting**: Generates 365-day forward predictions with 90% heteroscedastic prediction intervals (p05–p95) across 6 carrier frequency tiers and 10 standardized 3GPP operational metrics (60 distinct time series).
2. **4G Network Traffic Volume Forecasting**: Predicts 30-day macro network traffic volume (GB) with 80% and 95% confidence intervals, providing early warning alerts for carrier capacity thresholds (1.2M GB).
3. **Automated Model Tournament**: Competitively evaluates Damped Fourier Ridge Regression, Hybrid Residual Decomposition Trees, and Adaptive Seasonal Baselines against out-of-sample holdout test sets, guaranteeing $MASE \le 1.0$.

---

## 🌐 Subsystem Architecture

```
network_kpi_prediction/
├── main.py                               # Subsystem Unified CLI Dispatcher
├── requirements.txt                      # Subsystem Python Dependencies
├── README.md                             # Subsystem Documentation
│
├── kpi_prediction_pipeline/              # 3GPP Rel-17 Multi-Band Cellular Pipeline (60 Series)
│   ├── main.py                           # Unified CLI (split, train, plot, predict, test)
│   ├── train.py                          # Tournament Training & 365-Day Roll-Forward Engine
│   ├── plot.py                           # 300-DPI Publication Plot Engine
│   ├── predict.py                        # On-Demand Dynamic ML & Ribbon Inference CLI
│   ├── split.py                          # Chronological 3-Way Dataset Splitter
│   ├── src/
│   │   ├── config.py                     # Single Source of Truth for 3GPP KPIs, SLAs & Bands
│   │   ├── clean.py                      # Schema Validation, Null Handling & Boundary Clipping
│   │   ├── split.py                      # Monotonic Leak-Free Dataset Partitioning
│   │   ├── features.py                   # Damped Trends, Orthogonal Harmonics & Shift(1) Lags
│   │   ├── models.py                     # TargetTransformer, FourierRidge, HybridTrees, Quantiles
│   │   ├── plots.py                      # 80 Publication-Grade Matplotlib Dashboards (300 DPI)
│   │   └── export.py                     # Markdown Reports & RFC 8259 JSON Payloads
│   ├── data/
│   │   ├── carrier_ran_kpi_clean.csv     # Clean Multi-Band Telemetry
│   │   ├── splits/                       # Train (70%), Val (15%), Test (15%) Datasets
│   │   └── output/                       # 365-Day Predictions & model_metrics.csv/json
│   ├── models/                           # 60 Serialized Production Model Bundles (.joblib)
│   ├── plots/                            # 80 Generated Charts (Single, Grids, Multi-Band)
│   └── tests/                            # 41 Unit Tests (100% Pass Rate)
│
└── kpi_prediction_pipeline_traffic/      # Macro 4G Network Traffic Volume Pipeline
    ├── main.py                           # Sequential 6-Step Traffic Pipeline Runner
    ├── Year.csv                          # Historical 4G Telemetry (365 Days)
    ├── src/
    │   ├── clean.py                      # Robust IQR Seasonal Residual Anomaly Imputation
    │   ├── split.py                      # Chronological Train/Val/Test Splitter
    │   ├── features.py                   # Multi-Week Lags, Rolling Windows & Momentum Diff
    │   ├── models.py                     # Multi-Model Benchmarking (XGBoost, RF, Ridge, Naive)
    │   └── plots.py                      # 6 Production Visualizations (EDA, Splits, Cones)
    ├── data/                             # Partitioned Sets & 30-Day Forward Forecast CSV
    ├── plots/                            # 6 Generated Visual Figures (300 DPI)
    └── tests/                            # 7 Unit Tests (100% Pass Rate)
```

---

## 📊 3GPP Cellular Spectrum Bands & Standardized Metrics

### Spectrum Frequency Tiers
* **Band 350 MHz**: Macro Regional Coverage (~1,760 Cells)
* **Band 400 MHz**: Rural Sub-1GHz Cluster (~8 Cells)
* **Band 1556 MHz**: Mid-Band FDD Urban (~25 Cells)
* **Band 1700 MHz**: AWS/PCS Uplink Tier (~8 Cells)
* **Band 3500 MHz**: C-Band TDD Capacity Tier (~1,500 Cells)
* **Band 6200 MHz**: Upper 6GHz High-Throughput Cluster (~1,600 Cells)

### 3GPP Standardized KPIs
| Category | Metric | Unit | SLA Target | Transform |
| :--- | :--- | :--- | :--- | :--- |
| **Accessibility** | `rrc_setup_sr` | % | $\ge 99.0\%$ | Identity |
| **Accessibility** | `erab_estab_sr` | % | $\ge 99.0\%$ | Identity |
| **Retainability** | `erab_drop_rate` | % | $\le 0.50\%$ | Identity |
| **Mobility** | `handover_intra_sr` | ratio | $\ge 0.980$ | Identity |
| **Mobility** | `handover_sr` | % | $\ge 98.0\%$ | Identity |
| **Availability** | `availability_pct` | % | $\ge 99.5\%$ | Identity |
| **Capacity** | `dl_throughput_mbps` | Mbps | $\ge 5.0$ Mbps | `log1p` |
| **Capacity** | `ul_throughput_mbps` | Mbps | $\ge 1.0$ Mbps | `log1p` |
| **Capacity** | `connected_users` | UEs | Active traffic | `log1p` |
| **Survivability** | `downtime_sec` | cell-sec | $\le 3,600$s | `log1p` |

---

## ⚡ Quickstart & Execution

### 1. Installation
```powershell
pip install -r requirements.txt
```

### 2. Running Automated Test Suites (48 Tests)
```powershell
# Run Cellular Pipeline unit tests (41 tests)
python main.py test

# Run Traffic Pipeline unit tests (7 tests)
python -m unittest discover -s kpi_prediction_pipeline_traffic/tests -p "test_*.py" -v
```

### 3. Real-Time Dynamic Predictions
```powershell
# Live on-demand ML inference from model bundle
python main.py predict --carrier 3500 --kpi dl_throughput_mbps --days 7 --live

# Table lookup from 365-day precomputed forecast
python main.py predict --carrier 1556 --kpi rrc_setup_sr --days 7
```

### 4. Running the 4G Traffic Pipeline
```powershell
python main.py --pipeline traffic
```

---

## 🏆 Key Benchmark Results

* **Data Integrity**: **100% Physically Bounded** (0 NaNs, 0 infinities across 2,190 projection rows).
* **Holdout Skill**: **90.0%** of all 60 cellular series achieved positive out-of-sample skill score ($R^2_{bench} > 0$).
* **Model Tournament Selection**:
  * **FourierRidge**: 40.0% (Stationary harmonic series)
  * **AdaptiveBaseline**: 40.0% (Guaranteed holdout $MASE \le 1.0$)
  * **HybridEnsemble**: 20.0% (Non-linear user growth & capacity dynamics)
* **Traffic Forecast**: 30-day projected volume operates with **100% capacity safety margin** (no breach of 1.2M GB threshold).
