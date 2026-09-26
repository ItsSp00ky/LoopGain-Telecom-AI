# Network KPI Prediction — 3GPP & 4G Traffic Forecasting Platform

> **Samsung Innovation Campus (SIC) AI Capstone** // Loop Gain Team
> Dual-engine time-series forecasting platform for telecom network KPI prediction.

---

## Architecture Overview

This subsystem contains two independent forecasting pipelines:

| Pipeline | Directory | Purpose | Data Source |
|----------|-----------|---------|-------------|
| **3GPP Cellular KPI Forecast** | `cellular_kpi_forecast/` | Multi-band KPI prediction across 6 frequency bands, 10 KPIs, 60 series | `data/raw/erbs_cell_kpi_full_year.csv` |
| **4G Traffic Volume Forecast** | `traffic_volume_forecast/` | Macro 4G daily traffic volume forecasting with 30-day horizon | `data/raw/4g_traffic_volume_daily.csv` |

---

## Repository Structure

```
network_kpi_prediction/
├── README.md                              # This file
├── requirements.txt                       # Python dependencies
├── run_pipeline.py                        # Root CLI launcher (delegates to sub-pipelines)
│
├── data/
│   └── raw/
│       ├── erbs_cell_kpi_full_year.csv    # Raw ERBS cell KPI telemetry (1067 ERBS, 365 days)
│       └── 4g_traffic_volume_daily.csv    # Raw 4G daily traffic volume (264 days)
│
├── cellular_kpi_forecast/                 # 3GPP Rel-17 Multi-Band Cellular Pipeline (60 Series)
│   ├── run_cellular.py                    # Pipeline CLI orchestrator
│   ├── train_models.py                    # Stage 2: Model training & champion selection
│   ├── generate_plots.py                  # Stage 3: Publication-grade plot generation
│   ├── run_inference.py                   # On-demand model inference CLI
│   ├── run_split.py                       # Stage 1: Chronological dataset splitting
│   ├── src/
│   │   ├── kpi_config.py                  # 3GPP KPI specs, SLA thresholds, spectrum bands
│   │   ├── data_cleaning.py              # ERBS telemetry ingestion & cleaning
│   │   ├── feature_engineering.py         # Fourier harmonics, damped trends, AR features
│   │   ├── model_definitions.py           # Ridge, Hybrid Ensemble, Seasonal Baseline, Quantile
│   │   ├── temporal_splitting.py          # Chronological train/val/test splitting
│   │   ├── visualization.py              # 300-DPI publication plot engine
│   │   └── report_export.py              # MD/JSON/CSV export generators
│   ├── tests/                             # Unit & integration tests
│   ├── data/                              # Runtime data (generated)
│   ├── models/                            # Serialized model bundles (generated)
│   └── plots/                             # Plot images (generated)
│
├── traffic_volume_forecast/               # 4G Network Traffic Volume Pipeline
│   ├── run_traffic.py                     # Pipeline orchestrator
│   ├── src/
│   │   ├── data_cleaning.py              # Traffic data cleaning & anomaly treatment
│   │   ├── feature_engineering.py         # Time features & dataset preparation
│   │   ├── model_definitions.py           # Multi-model benchmarking & forecasting
│   │   ├── visualization.py              # Traffic plot generation
│   │   └── temporal_splitting.py          # Chronological splitting
│   ├── tests/                             # Traffic pipeline tests
│   ├── data/                              # Runtime data (generated)
│   └── plots/                             # Plot images (generated)
│
└── _archive/                              # Archived redundant files & previous outputs
```

---

## Quick Start

### Run the Cellular KPI Pipeline (Default)
```bash
python run_pipeline.py train                    # Train models + generate 365-day forecasts
python run_pipeline.py plot                     # Generate all 78 publication plots
python run_pipeline.py predict --carrier 3500 --kpi dl_throughput_mbps --days 7
```

### Run the Traffic Volume Pipeline
```bash
python run_pipeline.py --pipeline traffic       # Full end-to-end execution
```

### Run Tests
```bash
# Cellular pipeline tests
cd cellular_kpi_forecast && python run_cellular.py test

# Traffic pipeline tests
python -m unittest discover -s traffic_volume_forecast/tests -p "test_*.py" -v
```

---

## Data Assets

### Raw Data (`data/raw/`)
- **`erbs_cell_kpi_full_year.csv`** — 378,631 rows × 11 columns: daily cell-level KPIs from 1,067 ERBS base stations across 6 frequency bands (Sep 2025 → Sep 2026).
- **`4g_traffic_volume_daily.csv`** — 264 rows × 2 columns: daily aggregated 4G network traffic volume in GB (Jan → Sep 2026).

### KPI Columns (ERBS Data)
| Column | Description | Unit |
|--------|-------------|------|
| RRC Setup Success Rate | Radio Resource Control setup success | % |
| E-RAB Establishment Success Rate | Bearer initialization success | % |
| E-RAB Drop Rate | Bearer abnormal termination | % |
| Handover Success Rate (4G Intra System) | Intra-frequency handover | ratio |
| Handover Success Rate | Overall handover success | % |
| 4G Cell Av. (%) | Cell operational availability | % |
| E-UTRAN IP Throughput UE DL | Downlink throughput per UE | Mbps |
| E-UTRAN IP Throughput UE UL | Uplink throughput per UE | Mbps |
| Avg RRC Connected users | Average connected users | UEs |

---

## Model Architecture

### Cellular Pipeline: 3-Model Tournament
1. **Damped Fourier Ridge** — Regularized linear model with orthogonal Fourier harmonics
2. **Hybrid Trend-Seasonal Ensemble** — Ridge base + HistGBT residual decomposition
3. **Adaptive Seasonal Baseline** — Day-of-week median with recent operational window

Champion selection via MASE on validation set; holdout test verification.

### Traffic Pipeline: Multi-Model Benchmarking
Ridge, HGBT, Seasonal Naive — evaluated on WAPE, MAE, RMSE, MASE.
