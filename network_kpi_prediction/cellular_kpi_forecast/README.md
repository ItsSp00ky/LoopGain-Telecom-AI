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
| **Stage 2: Train** | `python train_model_definitions.py` | Benchmarks models on validation set, selects champions, and generates 365-day forward forecasts. |
| **Stage 3: Plot** | `python generate_visualization.py` | Generates 300-DPI publication charts in clean Light Theme across all bands & KPIs. |
| **Inference** | `python run_inference.py` | Queries point forecasts and 90% confidence ribbons (`p05` to `p95`) for any carrier and KPI. |
| **Master CLI** | `python run_cellular.py [cmd]`| Single entrypoint orchestrating all stages and test execution. |

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

# 5. Testing: Execute automated test suite (41 tests across all modules)
python run_cellular.py test
```

---

## 3. Clean Package Architecture

Every file is named precisely for its single responsibility:

```
cellular_kpi_forecast/
├── run_cellular.py                     # Master CLI dispatcher (split, train, plot, predict, test)
├── run_split.py                    # [Stage 1] Chronological 3-way dataset partitioner
├── train_model_definitions.py                    # [Stage 2] Model training, champion tournament & forecasting
├── generate_visualization.py                     # [Stage 3] 300-DPI publication plot generator
├── run_inference.py                  # On-demand prediction query CLI
├── README.md                   # Complete package documentation
├── requirements.txt            # Python dependencies
│
├── src/                        # Core Library Modules
│   ├── kpi_config.py               # 3GPP specifications, SLA targets, physical domain boundaries
│   ├── data_cleaning.py                # Telemetry sanitization, null imputation, bounds clipping
│   ├── run_split.py                # Temporal split algorithms with leak-free assertions
│   ├── feature_engineering.py             # Damped trend, Fourier harmonics, zero-lookahead lags
│   ├── model_definitions.py               # Ridge, Hybrid Ensemble, Baseline, Quantile bounds
│   ├── visualization.py                # Publication plotting engine (Light Theme)
│   └── report_export.py               # Markdown reports, clean CSVs, RFC 8259 JSON feeds
│
├── data/                       # Centralized Data Hub
│   ├── carrier_ran_kpi_clean.csv   # Master 3GPP RAN telemetry dataset (2,065 rows, 6 bands)
│   ├── splits/                 # train.csv (70%), val.csv (15%), test.csv (15%)
│   └── output/                 # 365-day forecasts and benchmark metrics
│
├── models/                     # 60 trained .joblib model bundles (6 bands x 10 KPIs)
├── plots/                      # 80 high-resolution generated charts
│
└── tests/                      # Modular Unit & Integration Tests (1:1 with src/)
    ├── test_kpi_config.py          # Tests src/kpi_config.py
    ├── test_data_cleaning.py           # Tests src/data_cleaning.py
    ├── test_run_split.py           # Tests src/run_split.py
    ├── test_feature_engineering.py        # Tests src/feature_engineering.py
    ├── test_model_definitions.py          # Tests src/model_definitions.py
    ├── test_visualization.py           # Tests src/visualization.py
    ├── test_report_export.py          # Tests src/report_export.py
    └── test_pipeline.py        # Consolidated integration test runner
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
