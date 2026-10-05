# 3GPP Cellular KPI Prediction Pipeline (`cellular_kpi_forecast`)

Standardized **3GPP Rel-17 NWDAF** (Network Data Analytics Function) and **O-RAN Non-RT RIC** cellular telemetry forecasting platform.

---

## 1. Quick Start

### Installation
```bash
pip install -r requirements.txt
```

### Pipeline Execution Stages

The pipeline consists of three sequential workflow stages and an on-demand prediction CLI:

| Pipeline Stage | Script | Purpose |
| :--- | :--- | :--- |
| **Stage 1: Split** | `python run_split.py` | Ingests sanitized telemetry & partitions chronologically (`70% Train` / `15% Val` / `15% Test`). |
| **Stage 2: Train** | `python train_models.py` | Benchmarks models on validation set, selects champions, and generates 365-day forward forecasts. |
| **Stage 3: Plot** | `python generate_plots.py` | Generates 300-DPI publication charts in clean Light Theme across all bands & KPIs. |
| **Inference** | `python run_inference.py` | Queries point forecasts and 90% confidence ribbons (`p05` to `p95`) for any carrier and KPI. |
| **Master CLI** | `python run_cellular.py [cmd]`| Single entrypoint orchestrating all stages and inference. |

---

## 2. Command-Line Interface (`run_cellular.py`)

Run all workflows directly from the unified command center:

```bash
# 1. Stage 1: Chronological dataset split
python run_cellular.py split

# 2. Stage 2: Train champion models and forecast 365 days
python run_cellular.py train

# 3. Stage 3: Generate publication plots (Light Theme)
python run_cellular.py plot --carrier 3500 --kpi dl_throughput_mbps

# 4. Inference: Query user traffic / throughput predictions
python run_cellular.py predict --carrier 3500 --kpi connected_users --days 7
```

---

## 3. Clean Package Architecture

Every file is named precisely for its single responsibility:

```
cellular_kpi_forecast/
├── run_cellular.py                 # Master CLI dispatcher (split, train, plot, predict)
├── run_split.py                    # [Stage 1] Chronological 3-way dataset partitioner
├── train_models.py                 # [Stage 2] Model training, champion tournament & forecasting
├── generate_plots.py               # [Stage 3] 300-DPI publication plot generator
├── run_inference.py                # On-demand prediction query CLI
├── README.md                       # Complete package documentation
│
├── src/                            # Core Library Modules
│   ├── kpi_config.py               # 3GPP specifications, SLA targets, physical domain boundaries
│   ├── data_cleaning.py            # Telemetry sanitization, null imputation, bounds clipping
│   ├── temporal_splitting.py       # Temporal split algorithms with leak-free assertions
│   ├── feature_engineering.py      # Damped trend, Fourier harmonics, zero-lookahead lags
│   ├── model_definitions.py        # Ridge, Hybrid Ensemble, Baseline, Quantile bounds
│   ├── visualization.py            # Publication plotting engine (Light Theme)
│   └── report_export.py           # Markdown reports, clean CSVs, RFC 8259 JSON feeds
│
├── data/                           # Centralized Data Hub
│   ├── carrier_ran_kpi_clean.csv   # Master 3GPP RAN telemetry dataset (2,065 rows, 6 bands)
│   ├── splits/                     # train.csv (70%), val.csv (15%), test.csv (15%)
│   └── output/                     # 365-day forecasts and benchmark metrics
│
├── models/                         # 60 trained .joblib model bundles (6 bands x 10 KPIs)
├── plots/                          # Core publication figures for technical report
│   ├── grids/                      # 6 Master Carrier Grids (Figures 2–7)
│   ├── multiband/                  # 10 Cross-Carrier Multi-Band Comparisons (Figures 10–19)
│   └── benchmarks/                 # 2 Model Performance Benchmarks (Figures 8–9)
└── artifacts/                      # Decoupled Standalone Artifacts & Manifests
    ├── individual_plots_index.csv  # Index manifest (carrier_id, kpi_name, status, file_path)
    ├── individual_plots_index.json # Machine-readable JSON manifest
    └── plots/individual/           # 60 standalone carrier-KPI series plots for dashboard/appendix
```

---

## 4. Predicted 3GPP Rel-17 KPIs

| Category | KPI Key | Description | Unit | SLA Target |
| :--- | :--- | :--- | :--- | :--- |
| **Capacity & Traffic** | `connected_users` | Active simultaneous users (UEs) | UEs | Active traffic |
| | `dl_throughput_mbps` | Downlink user data throughput | Mbps | $\ge 5.0$ Mbps |
| | `ul_throughput_mbps` | Uplink user data throughput | Mbps | $\ge 1.0$ Mbps |
| **Accessibility** | `rrc_setup_sr` | RRC connection establishment SR | % | $\ge 99.0\%$ |
| | `erab_estab_sr` | E-RAB bearer initialization SR | % | $\ge 99.0\%$ |
| **Retainability** | `erab_drop_rate` | Bearer session abnormal drop rate | % | $\le 0.5\%$ |
| **Mobility** | `handover_sr` | Handover execution success rate | % | $\ge 98.0\%$ |
| | `handover_intra_sr` | Intra-frequency sector transition SR | ratio | $\ge 0.98$ |
| **Availability** | `availability_pct` | Cell radio operational uptime | % | $\ge 99.5\%$ |
| | `downtime_sec` | Cluster outage downtime duration | cell-sec | $\le 3,600$ s |
