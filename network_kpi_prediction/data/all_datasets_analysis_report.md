# Network KPI Prediction — Multi-Tier Telemetry Data Catalog

> **Samsung Innovation Campus (SIC) Capstone // Team Loop Gain**  
> Comprehensive audit, domain profiling, and cross-dataset synthesis across all telecommunication datasets.

---

## 1. Executive Summary & Dataset Inventory

The `network_kpi_prediction` subsystem operates on a multi-tier hierarchy of telecom data assets:

| ID | Dataset Title | Granularity | Observations | Features | Temporal Span | Size |
|---|---|---|---|---|---|---|
| `traffic_volume_daily` | **4G Daily Network Accumulated Traffic Volume** | Daily Network-Wide Aggregate | 264 | 2 | 2026-01-01 to 2026-09-21 (264d) | 5.8 KB |
| `macro_network_kpis` | **Macro Network 4G Radio KPIs (Network-Wide)** | Daily Network-Wide Aggregate | 363 | 8 | 2025-09-18 to 2026-09-17 (363d) | 17.8 KB |
| `carrier_earfcndl_telemetry` | **Carrier-Level (EARFCNDL) 4G Telemetry** | Daily Carrier / Frequency Band (EARFCNDL) | 2,065 | 12 | 2025-09-18 to 2026-09-17 (363d) | 146.0 KB |
| `erbs_cell_summer_window` | **Summer High-Density ERBS Cell Telemetry (120-Day Window)** | Daily Cell / Base Station Node (1,060 ERBS) | 125,779 | 11 | 2026-05-23 to 2026-09-19 (120d) | 8.29 MB |
| `erbs_cell_full_year` | **Full-Year ERBS Cell Telemetry (363 Days)** | Daily Cell / Base Station Node (1,067 ERBS) | 378,631 | 11 | 2025-09-20 to 2026-09-19 (363d) | 24.97 MB |

---

## 2. Telecommunication Granularity Hierarchy

```
LEVEL 1: Macro Network Aggregation (Daily Network-Wide Total)
├── traffic_volume_daily       [264 days] -> Overall 4G Traffic Volume (GB)
└── macro_network_kpis         [363 days] -> 7 Core Network-Wide 3GPP KPIs

LEVEL 2: Carrier Spectrum Band Partition (EARFCNDL)
└── carrier_earfcndl_telemetry [2,065 rows] -> 6 Spectrum Bands (350, 400, 1556, 1700, 3500, 6200 MHz)
    ├── 10 Standard 3GPP KPIs (RRC, E-RAB, Handover, Throughput, Users, Availability)
    └── pmCellDowntimeMan (Exact Operational Manual Downtime Seconds)

LEVEL 3: Physical Base Station / Cell Node Level (ERBS)
├── erbs_cell_full_year        [378,631 rows] -> 1,067 ERBS Nodes, 363 Days
└── erbs_cell_summer_window    [125,779 rows] -> 1,060 ERBS Nodes, 120 Days (Peak Summer Window)
```

---

## 3. Dataset In-Depth Profiling

### `traffic_volume_daily`: 4G Daily Network Accumulated Traffic Volume
- **Granularity**: Daily Network-Wide Aggregate
- **Description**: Macro-level aggregated 4G data volume in GB across all sectors and user equipment.
- **File Path**: `data/4g_traffic_volume_daily.csv`
- **Dimensions**: 264 rows × 2 columns

#### Statistical Summary

| Column Name | Type | Mean | Std | Min | Median | Max | Nulls (%) |
|---|---|---|---|---|---|---|---|
| `4G Overall Accumulated Data Volume (GB)` | Numeric | 1,012,613.0464 | 55,458.9827 | 727,726.39 | 1,015,673.12 | 1,135,857.32 | 0.0% |

### `macro_network_kpis`: Macro Network 4G Radio KPIs (Network-Wide)
- **Granularity**: Daily Network-Wide Aggregate
- **Description**: Macro-level network-wide daily 3GPP radio KPIs covering 7 core metrics across the entire 4G grid.
- **File Path**: `data/macro_network_kpis_daily.csv`
- **Dimensions**: 363 rows × 8 columns

#### Statistical Summary

| Column Name | Type | Mean | Std | Min | Median | Max | Nulls (%) |
|---|---|---|---|---|---|---|---|
| `RRC Setup Success Rate` | Numeric | 99.6156 | 0.1539 | 97.93 | 99.65 | 99.8 | 0.0% |
| `E-RAB Establishment Success Rate` | Numeric | 99.6785 | 0.0422 | 99.44 | 99.67 | 99.77 | 0.0% |
| `E-RAB Drop Rate` | Numeric | 0.2451 | 0.0682 | 0.1 | 0.24 | 0.59 | 0.0% |
| `Handover Success Rate ( 4G Intra System)` | Numeric | 0.9751 | 0.0122 | 0.93 | 0.98 | 0.99 | 0.0% |
| `Handover Success Rate` | Numeric | 97.4991 | 1.1604 | 92.78 | 97.56 | 99.06 | 0.0% |
| `E-UTRAN IP Throughput UE DL` | Numeric | 6.6208 | 1.218 | 2.52 | 6.67 | 11.67 | 0.0% |
| `E-UTRAN IP Throughput UE UL` | Numeric | 1.0065 | 0.1826 | 0.3 | 1.0 | 1.42 | 0.0% |

### `carrier_earfcndl_telemetry`: Carrier-Level (EARFCNDL) 4G Telemetry
- **Granularity**: Daily Carrier / Frequency Band (EARFCNDL)
- **Description**: Ground-truth multi-band radio telemetry partitioned by 3GPP EARFCNDL channels (350, 400, 1556, 1700, 3500, 6200 MHz), including manual downtime seconds.
- **File Path**: `data/carrier_earfcndl_kpi_daily.csv`
- **Dimensions**: 2,065 rows × 12 columns
- **Frequency Bands (EARFCNDL)**: `[350, 400, 1556, 1700, 3500, 6200]`

#### Statistical Summary

| Column Name | Type | Mean | Std | Min | Median | Max | Nulls (%) |
|---|---|---|---|---|---|---|---|
| `earfcndl` | Numeric | 2,387.447 | 2,046.2885 | 350.0 | 1,700.0 | 6,200.0 | 0.0% |
| `RRC Setup Success Rate` | Numeric | 99.5707 | 0.3168 | 92.75 | 99.67 | 99.86 | 1.65% |
| `E-RAB Establishment Success Rate` | Numeric | 99.5628 | 0.2761 | 97.96 | 99.7 | 99.86 | 1.65% |
| `E-RAB Drop Rate` | Numeric | 0.331 | 0.357 | 0.07 | 0.2 | 4.32 | 1.65% |
| `Handover Success Rate ( 4G Intra System)` | Numeric | 0.9787 | 0.0153 | 0.86 | 0.98 | 1.0 | 1.65% |
| `Handover Success Rate` | Numeric | 97.8206 | 1.4893 | 86.45 | 98.38 | 100.0 | 1.65% |
| `4G Cell Av. (%)` | Numeric | 92.6036 | 13.4049 | 0.0 | 95.29 | 100.0 | 0.0% |
| `E-UTRAN IP Throughput UE DL` | Numeric | 7.3758 | 3.1885 | 1.25 | 7.56 | 55.12 | 1.65% |
| `E-UTRAN IP Throughput UE UL` | Numeric | 1.4252 | 0.8257 | 0.09 | 1.39 | 5.58 | 1.65% |
| `Avg RRC Connected users` | Numeric | 15.0866 | 9.3928 | 3.18 | 10.38 | 36.29 | 1.65% |
| `pmCellDowntimeMan` | Numeric | 6,547,770.0872 | 7,731,092.2998 | 0.0 | 1,641,696.0 | 22,197,740.0 | 0.0% |

### `erbs_cell_summer_window`: Summer High-Density ERBS Cell Telemetry (120-Day Window)
- **Granularity**: Daily Cell / Base Station Node (1,060 ERBS)
- **Description**: Operational summer window dataset spanning 120 days of peak seasonal load across 1,060 physical ERBS nodes.
- **File Path**: `data/erbs_cell_kpi_summer_120d.csv`
- **Dimensions**: 125,779 rows × 11 columns
- **Physical ERBS Nodes**: `1,060` base stations

#### Statistical Summary

| Column Name | Type | Mean | Std | Min | Median | Max | Nulls (%) |
|---|---|---|---|---|---|---|---|
| `ERBS Id` | Categorical (1060 unique) | — | — | — | — | Sample: [BTWRM1, CTWRM1, DAS09M1] | 100.0% |
| `RRC Setup Success Rate` | Numeric | 99.613 | 0.5269 | 29.91 | 99.66 | 100.0 | 0.19% |
| `E-RAB Establishment Success Rate` | Numeric | 99.6296 | 0.4606 | 0.0 | 99.66 | 100.0 | 0.2% |
| `E-RAB Drop Rate` | Numeric | 0.2764 | 0.3337 | 0.0 | 0.21 | 20.0 | 0.2% |
| `Handover Success Rate ( 4G Intra System)` | Numeric | 0.9775 | 0.0375 | 0.0 | 0.99 | 1.0 | 0.43% |
| `Handover Success Rate` | Numeric | 97.7733 | 3.7543 | 0.0 | 98.74 | 100.0 | 0.43% |
| `4G Cell Av. (%)` | Numeric | 91.7281 | 17.2235 | 0.0 | 100.0 | 100.0 | 0.0% |
| `E-UTRAN IP Throughput UE DL` | Numeric | 9.7176 | 6.8482 | 0.0 | 8.41 | 142.8 | 0.21% |
| `E-UTRAN IP Throughput UE UL` | Numeric | 1.3676 | 1.2937 | 0.0 | 1.12 | 28.18 | 0.21% |
| `Avg RRC Connected users` | Numeric | 15.7448 | 8.1632 | 0.0 | 14.74 | 104.97 | 0.05% |

### `erbs_cell_full_year`: Full-Year ERBS Cell Telemetry (363 Days)
- **Granularity**: Daily Cell / Base Station Node (1,067 ERBS)
- **Description**: Full-year cell-level telemetry spanning 363 days across 1,067 physical ERBS nodes totaling 378,631 observation records.
- **File Path**: `data/erbs_cell_kpi_full_year.csv`
- **Dimensions**: 378,631 rows × 11 columns
- **Physical ERBS Nodes**: `1,067` base stations

#### Statistical Summary

| Column Name | Type | Mean | Std | Min | Median | Max | Nulls (%) |
|---|---|---|---|---|---|---|---|
| `ERBS Id` | Categorical (1067 unique) | — | — | — | — | Sample: [BTWRM1, CTWRM1, DAS09M1] | 100.0% |
| `RRC Setup Success Rate` | Numeric | 99.6585 | 0.4683 | 19.56 | 99.7 | 100.0 | 0.36% |
| `E-RAB Establishment Success Rate` | Numeric | 99.6635 | 0.5712 | 0.0 | 99.7 | 100.0 | 0.36% |
| `E-RAB Drop Rate` | Numeric | 0.2439 | 0.35 | 0.0 | 0.18 | 20.0 | 0.37% |
| `Handover Success Rate ( 4G Intra System)` | Numeric | 0.9779 | 0.0424 | 0.0 | 0.99 | 1.0 | 0.54% |
| `Handover Success Rate` | Numeric | 97.8222 | 4.2408 | 0.0 | 98.76 | 100.0 | 0.54% |
| `4G Cell Av. (%)` | Numeric | 93.3443 | 18.0771 | 0.0 | 100.0 | 100.0 | 0.0% |
| `E-UTRAN IP Throughput UE DL` | Numeric | 11.2858 | 7.0197 | 0.0 | 10.15 | 151.44 | 0.37% |
| `E-UTRAN IP Throughput UE UL` | Numeric | 1.482 | 1.2762 | 0.0 | 1.24 | 47.0 | 0.38% |
| `Avg RRC Connected users` | Numeric | 15.4284 | 8.4923 | 0.0 | 14.12 | 104.97 | 0.28% |

---

## 4. Cross-Dataset Telecommunication Dynamics & Correlations

### 4.1 Traffic Volume vs. Radio Network Conditions

Analysis of overlapping observation days between macro 4G traffic volume and network radio KPIs reveals key physical network load behaviors:

| Radio Metric | Pearson Correlation (r) with Traffic Volume | Engineering Interpretation |
|---|---|---|
| `E-UTRAN IP Throughput UE DL` | **-0.3202** | Cell Congestion: High aggregate traffic volume saturates PRBs, reducing individual UE downlink throughput. |
| `E-UTRAN IP Throughput UE UL` | **-0.3176** | Uplink Scheduling Limits: High concurrent usage increases interference and limits uplink throughput. |
| `E-RAB Drop Rate` | **-0.2230** | Radio Link Robustness: Slight inverse drop rate correlation indicates traffic growth during stable operational periods. |
| `E-RAB Establishment Success Rate` | **-0.2183** | Connection Stability: Consistent admission control across normal and peak loads. |
| `Handover Success Rate ( 4G Intra System)` | **-0.1466** | Mobility Robustness: Intra-frequency handover maintains high stability even under heavier traffic. |
| `Handover Success Rate` | **-0.1323** | Inter-Frequency Mobility: Overall handover remains above 97% under traffic fluctuations. |
| `RRC Setup Success Rate` | **+0.2326** | Signaling Channel Capacity: Positive correlation reflects expanded carrier capacity and active user growth. |
| `date` | **+0.5494** | Telecommunication network behavioral correlation. |

### 4.2 ERBS Subset Verification (Summer Window vs. Full Year)

- **Summer Window Records**: 125,779
- **Full Year Records**: 378,631
- **Exact Match Overlap**: 125,779 (100.0%)
- **Conclusion**: The summer window (`erbs_cell_kpi_summer_120d.csv`) is verified to be a mathematically exact 100.0% subset of the full-year telemetry (`erbs_cell_kpi_full_year.csv`), specifically isolated for peak-load summer operational stress analysis.

---

## 5. Pipeline Ingestion & Multi-Source Utilization

All 5 datasets are seamlessly integrated into the `network_kpi_prediction` pipeline:

1. **`traffic_volume_daily`**: Directly feeds the 4G Traffic Volume Forecasting model.
2. **`macro_network_kpis`**: Available as exogenous features for traffic volume and as macro network forecast targets.
3. **`carrier_earfcndl_telemetry`**: Direct carrier ingestion with ground-truth `pmCellDowntimeMan` and 6 frequency bands.
4. **`erbs_cell_full_year`**: Cell-level bottom-up aggregation across 1,067 ERBS nodes.
5. **`erbs_cell_summer_window`**: High-load operational window benchmarking.
