# Network KPI Prediction — 3GPP & 4G Traffic Forecasting Platform

> **Samsung Innovation Campus (SIC) AI Capstone** // Loop Gain Team
> Dual-engine time-series forecasting platform for telecom network KPI prediction.

---

## Architecture Overview

This subsystem contains two independent forecasting pipelines:

| Pipeline / Engine | Directory | Purpose | Primary Data Source |
|---|---|---|---|
| **3GPP Cellular KPI Forecast** | `cellular_kpi_forecast/` | Multi-band KPI prediction across 6 frequency bands, 10 KPIs, 60 series | `data/carrier_earfcndl_kpi_daily.csv` |
| **4G Traffic Volume Forecast** | `traffic_volume_forecast/` | Macro 4G traffic volume forecasting with univariate & multivariate modes | `data/4g_traffic_volume_daily.csv` |
| **Physical ERBS Node Intelligence** | `erbs_node_analytics/` | SLA health scorecard, sleeping cell detection, clustering (1,067 towers) | `data/erbs_cell_kpi_full_year.csv` |

---

## Repository Structure

```
network_kpi_prediction/
├── README.md                              # This file
├── requirements.txt                       # Python dependencies
├── run_pipeline.py                        # Root CLI launcher (delegates to sub-pipelines)
├── data_catalog.py                        # Data catalog and profiler
│
├── data/                                  # Multi-tier cleaned & standardized telemetry assets
│   ├── 4g_traffic_volume_daily.csv        # 4G daily network traffic volume (264 days)
│   ├── macro_network_kpis_daily.csv       # Network-wide 4G radio KPIs (363 days)
│   ├── carrier_earfcndl_kpi_daily.csv     # Carrier-level EARFCNDL telemetry (6 bands, 2,065 rows)
│   ├── erbs_cell_kpi_summer_120d.csv      # Summer 120-day high-density ERBS telemetry (125,779 rows)
│   └── erbs_cell_kpi_full_year.csv        # Full-year cell-level telemetry (1,067 ERBS, 378,631 rows)
│
├── artifacts/                             # Decoupled Standalone Artifacts & Manifests
│   ├── individual_plots_index.csv         # Standalone series index manifest (60 KPIs)
│   ├── individual_plots_index.json        # Machine-readable JSON manifest
│   └── plots/individual/                  # 60 standalone carrier-KPI series plots
│
├── erbs_node_analytics/                  # Physical ERBS Base Station Intelligence & ST-GNN
│   ├── run_erbs_analytics.py              # Subsystem CLI orchestrator (audit, gnn, inspect)
│   ├── src/
│   │   ├── node_profiler.py               # 3GPP SLA compliance & IsolationForest sleeping cells
│   │   ├── node_clustering.py             # Behavioral PCA clustering & operational personas
│   │   ├── summer_stress.py               # 120-day summer thermal & capacity degradation
│   │   ├── topology_graph.py              # Zero-GPS 1,067-node graph & Laplacian construction
│   │   ├── spectral_gnn.py                # Spatio-Temporal GNN (ChebNet + Dynamic Attention)
│   │   ├── gnn_visualizer.py              # Adjacency heatmap, spillover CDF, attention graphs
│   │   ├── visualizer.py                  # 300-DPI publication figures
│   │   └── export_synergy.py              # Cross-subsystem bridge dataset exports
│   └── plots/                             # Generated ERBS publication figures
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
│   └── plots/                             # Grids, multiband, and benchmark figures
│
├── traffic_volume_forecast/               # 4G Network Traffic Volume Pipeline
│   ├── run_traffic.py                     # Pipeline orchestrator
│   ├── src/
│   │   ├── data_cleaning.py              # Traffic data cleaning & anomaly treatment
│   │   ├── feature_engineering.py         # Time features & dataset preparation
│   │   ├── model_definitions.py           # Multi-model benchmarking & forecasting
│   │   ├── visualization.py              # Consolidated 3-panel traffic diagnostic plots
│   │   └── temporal_splitting.py          # Chronological splitting
│   └── plots/                             # Plot images (traffic_diagnostic_overview.png)
```

---

## Quick Start

### Run Physical ERBS Node Intelligence & Spatial GNN (1,067 Base Stations)
```bash
python run_pipeline.py erbs-audit               # Full SLA audit, sleeping cell detection, K-Means clustering & summer stress
python run_pipeline.py gnn                      # Train & benchmark Spatio-Temporal GNN (ChebNet + Dynamic Attention)
python run_pipeline.py inspect --erbs BTWRM1    # Instant engineering diagnostic scorecard, persona & spatial neighbors
```

### Run Multivariate 4G Traffic Volume Forecasting (Exogenous Radio KPIs)
```bash
python run_pipeline.py traffic-multi            # Benchmark multivariate exogenous model against univariate baseline
```

### Run the Cellular KPI Pipeline (Default)
```bash
python run_pipeline.py train                    # Train models + generate 365-day forecasts
python run_pipeline.py plot                     # Generate master grids, multiband comparisons, and manifest
python run_pipeline.py predict --carrier 3500 --kpi dl_throughput_mbps --days 7
```

### Run the Traffic Volume Pipeline
```bash
python run_pipeline.py --pipeline traffic       # Full end-to-end execution
```

### Inspect & Profile All Datasets
```bash
python run_pipeline.py catalog                  # Automated audit & statistical synthesis of all datasets in 'data/'
```

---

## Multi-Tier Telemetry Data Assets (`data/`)

The platform works natively with all 5 telecommunication datasets organized across three structural hierarchy levels:

| Hierarchy Level | Dataset File | Granularity | Observations | Key Attributes |
|---|---|---|---|---|
| **Level 1 (Macro)** | `4g_traffic_volume_daily.csv` | Daily Network Aggregate | 264 days | Overall 4G Data Volume (GB) |
| **Level 1 (Macro)** | `macro_network_kpis_daily.csv` | Daily Network Aggregate | 363 days | 7 core 3GPP Radio KPIs |
| **Level 2 (Carrier)** | `carrier_earfcndl_kpi_daily.csv` | Carrier Band (EARFCNDL) | 2,065 rows | 6 Frequency Bands + `pmCellDowntimeMan` |
| **Level 3 (Cell/Node)**| `erbs_cell_kpi_summer_120d.csv` | Physical ERBS (1,060 nodes)| 125,779 rows | 120-Day Summer Peak Operational Window |
| **Level 3 (Cell/Node)**| `erbs_cell_kpi_full_year.csv` | Physical ERBS (1,067 nodes)| 378,631 rows | Full-Year 363-Day Cell Telemetry |

### Direct Workflow with Any Dataset (`--dataset`)
```bash
# Work directly with ground-truth EARFCNDL telemetry:
python run_pipeline.py train --dataset earfcndl

# Work with the 120-day summer operational stress window:
python run_pipeline.py train --dataset summer

# Work with full-year cell-level telemetry:
python run_pipeline.py train --dataset full

# Work with macro network 4G KPIs:
python run_pipeline.py train --dataset macro

# Work with 4G traffic volume data:
python run_pipeline.py --pipeline traffic train --dataset traffic
```

---

## Model Architecture

### Cellular Pipeline: 3-Model Tournament
1. **Damped Fourier Ridge** — Regularized linear model with orthogonal Fourier harmonics
2. **Hybrid Trend-Seasonal Ensemble** — Ridge base + HistGBT residual decomposition
3. **Adaptive Seasonal Baseline** — Day-of-week median with recent operational window

Champion selection via MASE on validation set; holdout test verification.

### Traffic Pipeline: Multi-Model Benchmarking
Ridge, HGBT, Seasonal Naive — evaluated on WAPE, MAE, RMSE, MASE.
