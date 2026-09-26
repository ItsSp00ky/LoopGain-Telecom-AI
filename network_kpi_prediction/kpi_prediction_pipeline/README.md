# 3GPP Cellular KPI Prediction Pipeline (`kpi_prediction_pipeline`)

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
| **Stage 1: Split** | `python split.py` | Ingests sanitized telemetry & partitions chronologically (`70% Train` / `15% Val` / `15% Test`). |
| **Stage 2: Train** | `python train.py` | Benchmarks models on validation set, selects champions, and generates 365-day forward forecasts. |
| **Stage 3: Plot** | `python plot.py` | Generates 300-DPI publication charts in clean Light Theme across all bands & KPIs. |
| **Inference** | `python predict.py` | Queries point forecasts and 90% confidence ribbons (`p05` to `p95`) for any carrier and KPI. |
| **Master CLI** | `python main.py [cmd]`| Single entrypoint orchestrating all stages and test execution. |

---

## 2. Command-Line Interface (`main.py`)

Run all workflows directly from the unified command center:

```bash
# 1. Stage 1: Chronological dataset split
python main.py split

# 2. Stage 2: Train champion models and forecast 365 days
python main.py train

# 3. Stage 3: Generate publication plots (Light Theme)
python main.py plot --carrier 3500 --kpi dl_throughput_mbps

# 4. Inference: Query user traffic / throughput predictions
python main.py predict --carrier 3500 --kpi connected_users --days 7

# 5. Testing: Execute automated test suite (41 tests across all modules)
python main.py test
```

---

## 3. Clean Package Architecture

Every file is named precisely for its single responsibility:

```
kpi_prediction_pipeline/
├── main.py                     # Master CLI dispatcher (split, train, plot, predict, test)
├── split.py                    # [Stage 1] Chronological 3-way dataset partitioner
├── train.py                    # [Stage 2] Model training, champion tournament & forecasting
├── plot.py                     # [Stage 3] 300-DPI publication plot generator
├── predict.py                  # On-demand prediction query CLI
├── README.md                   # Complete package documentation
├── requirements.txt            # Python dependencies
│
├── src/                        # Core Library Modules
│   ├── config.py               # 3GPP specifications, SLA targets, physical domain boundaries
│   ├── clean.py                # Telemetry sanitization, null imputation, bounds clipping
│   ├── split.py                # Temporal split algorithms with leak-free assertions
│   ├── features.py             # Damped trend, Fourier harmonics, zero-lookahead lags
│   ├── models.py               # Ridge, Hybrid Ensemble, Baseline, Quantile bounds
│   ├── plots.py                # Publication plotting engine (Light Theme)
│   └── export.py               # Markdown reports, clean CSVs, RFC 8259 JSON feeds
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
    ├── test_config.py          # Tests src/config.py
    ├── test_clean.py           # Tests src/clean.py
    ├── test_split.py           # Tests src/split.py
    ├── test_features.py        # Tests src/features.py
    ├── test_models.py          # Tests src/models.py
    ├── test_plots.py           # Tests src/plots.py
    ├── test_export.py          # Tests src/export.py
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
