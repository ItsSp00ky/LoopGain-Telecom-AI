# AI Antenna Cell Site Placement Optimization
### Samsung Innovation Campus (SIC) Capstone Project – Team Loop Gain

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/badge/Package_Manager-uv-purple.svg)](https://github.com/astral-sh/uv)
[![AI/ML](https://img.shields.io/badge/Models-LightGBM%20%7C%20XGBoost%20%7C%20RandomForest-orange.svg)](#)
[![Geospatial](https://img.shields.io/badge/GIS-WorldPop%20%7C%20SRTM_DEM%20%7C%20UN_OCHA-green.svg)](#)
[![ROC-AUC](https://img.shields.io/badge/Suitability_ROC--AUC-0.9862-brightgreen.svg)](#)

An intelligent geospatial Machine Learning and network planning system engineered to predict and optimize the most suitable geographic locations for deploying new cellular antenna towers across Libya. The platform balances high-resolution gridded population density, terrain elevation and prominence, road infrastructure accessibility, existing multi-carrier network topology, and coverage deficits.

---

## 👥 Team Loop Gain

| Member | Email | Role |
| :--- | :--- | :--- |
| **Ahmed Gali** | [ahmed.gali.info@gmail.com](mailto:ahmed.gali.info@gmail.com) | Machine Learning & Data Engineering |
| **Taha Elkhazmi** | [Elkhazmittt@gmail.com](mailto:Elkhazmittt@gmail.com) | AI Systems & Architecture |
| **Mahmoud Almabrouk** | [mahmab90@gmail.com](mailto:mahmab90@gmail.com) | Data Modeling & Evaluation |
| **Maher Alqadhi** | [maher9maher9@gmail.com](mailto:maher9maher9@gmail.com) | Systems Development |
| **Mohamed Khalaf** | [moha.khalaf@uot.edu.ly](mailto:moha.khalaf@uot.edu.ly) | AI Research & Analysis |
| **Ali Marghem** | [al.marghem@uot.edu.ly](mailto:al.marghem@uot.edu.ly) | AI Research & Verification |

---

## 📌 Executive Summary & Key Results

- **Data Cleaning & Deduplication**:
  - Identified and repaired a critical regional scoping collision in legacy SQLite data (where site IDs repeating across RNC/TAC regions caused distant antennas up to 812 km apart to be collapsed).
  - Consolidated **4,258** crowdsourced radio observations into **2,338** unique radio antennas with **<0.11m** spatial consistency.
  - Collocated multi-technology antennas (threshold: 50m) into **2,115** physical cellular mast sites, uncovering **109** multi-technology collocated sites and **45** multi-operator infrastructure sharing sites between Libyana and Al-Madar.
- **External Geospatial Intelligence for Libya**:
  - Integrated **WorldPop 2020** 1km gridded population density (UN adjusted).
  - Integrated **SRTM Digital Elevation Model (DEM)** at 250m resolution for elevation, slope, and 3km viewshed prominence.
  - Integrated **UN OCHA Transportation Network** (4,141 road segments) and **Populated Places** across all 22 Libyan Municipalities (Baladiyat).
- **Machine Learning Benchmark**:
  - **Champion Model**: LightGBM Classifier with **0.9862 ROC-AUC**, **0.9794 PR-AUC**, and **95.19% Accuracy** across 5-fold stratified cross-validation.
  - **Equipment Recommender**: Random Forest multi-tier classifier achieving **89.55% Accuracy** in recommending equipment tiers (`Urban_HighCapacity_Macro`, `Suburban_Standard_Macro`, `Rural_Coverage_Macro`).
- **Placement Recommendations**:
  - Evaluated **22,605** candidate locations across Libya, identifying **4,467** unserved coverage gaps and ranking the **Top 50 High-Priority New Cell Placements**.

---

## 🌐 System Architecture

```
antenna_cell_placement/
├── pyproject.toml                     # uv package configuration & CLI entry points
├── uv.lock                            # Deterministic dependency lockfile
├── README.md                          # Module documentation & benchmark report
│
├── Libyan_cells_dataset/              # Raw crowdsourced telecom datasets
│   ├── cells.sqlite3                  # Relational database (2,291 raw towers)
│   ├── cells.json                     # Raw LTE observations (1,318 records)
│   ├── cells.geojson                  # Legacy physical sites GeoJSON
│   └── cells_map.html                 # Legacy site map
│
├── data/
│   ├── external/                      # Downloaded Libya Geospatial Datasets
│   │   ├── lby_pd_2020_1km.tif        # WorldPop 1km Population Density GeoTIFF
│   │   ├── dem/DEM/lyb_strm_250m      # SRTM 250m Digital Elevation Model
│   │   ├── roads/LYB_Roads.shp        # UN OCHA Libya Highway & Road Network
│   │   └── admin_boundaries/         # Libya Admin 0, Admin 1, Admin 2 & Settlements
│   │
│   └── cleaned/                       # Processed, Enriched & Parquet Datasets
│       ├── cleaned_radio_towers.csv   # 2,338 deduplicated antennas with RF attributes
│       ├── cleaned_physical_sites.csv # 2,115 physical mast sites
│       ├── cleaned_physical_sites.geojson
│       ├── cleaned_cells_combined.parquet  # 52-feature master ML dataset
│       └── cleaned_cells_map.html     # Interactive Leaflet map
│
├── models/                            # Serialized Champion AI Models
│   ├── cell_placement_suitability_model.joblib  # LightGBM Classifier (0.9862 ROC-AUC)
│   └── equipment_recommendation_model.joblib    # Multi-tier Equipment Classifier
│
├── eval_reports/                      # Evaluation Reports, Benchmark Metrics & Maps
│   ├── model_benchmark.json           # Model validation metrics
│   ├── suitability_roc_curve.png      # ROC curve visualization
│   ├── suitability_feature_importance.png # Split gain feature importance chart
│   ├── suitability_confusion_matrix.png   # Classification confusion matrix
│   ├── recommended_cell_placements.csv    # Prioritized deployment recommendations
│   ├── recommended_cell_placements.geojson
│   └── libya_cell_coverage_map.html   # Master coverage & recommendation map
│
└── src/antenna_cell_placement/        # Python Package Source
    ├── __init__.py                    # Package exports
    ├── config.py                      # Paths, CRS constants, and parameters
    ├── data_cleaning.py               # Parsing, deduplication & mast clustering
    ├── feature_engineering.py         # Multi-layer raster & vector extraction
    ├── placement_model.py             # LightGBM & XGBoost training & cross-validation
    ├── site_optimizer.py              # Coverage gap optimizer & ranking engine
    ├── map_visualizer.py              # Folium / Leaflet map generator
    ├── placement.py                   # Programmatic Python API
    └── cli.py                         # Rich CLI command-line interface
```

---

## 📊 Model Evaluation & Benchmarks

Models were evaluated using 5-fold Stratified Cross-Validation on a balanced dataset of 2,115 confirmed cell sites and 2,500 systematically generated candidate locations across Libya's transportation corridors and settlement perimeters:

| Model | ROC-AUC | PR-AUC | Accuracy | F1-Score | Precision | Recall | Brier Score |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **LightGBM Classifier (Champion)** | **0.9862** | **0.9794** | **95.19%** | **0.9481** | **93.57%** | **96.08%** | **0.0379** |
| **XGBoost Classifier** | 0.9867 | 0.9796 | 95.32% | 0.9494 | 93.81% | 96.10% | 0.0371 |

### Top Geospatial Drivers for Cell Site Placement

1. **`dist_to_nearest_site_m`**: Spatial inter-site distance and network density.
2. **`population_sum_5km`**: Population catchment demand within standard macro cell coverage radius.
3. **`dist_to_nearest_road_m`**: Infrastructure buildability and vehicular coverage.
4. **`elevation_prominence_3km`**: Height above average terrain (HAAT), governing radio line-of-sight propagation.
5. **`population_density_1km`**: Local density governing cell traffic load and micro-cell offloading requirements.

---

## 🚀 Quick Start Guide

### 1. Installation with `uv`

```bash
# Navigate to the antenna module
cd antenna_cell_placement

# Sync dependencies
uv sync
```

### 2. Run Commands via CLI

```bash
# 1. Clean raw SQLite/JSON data and consolidate physical mast sites
uv run antenna-placement clean

# 2. Extract multi-layer geospatial features (WorldPop, SRTM DEM, OCHA roads)
uv run antenna-placement features

# 3. Train AI placement suitability and equipment recommendation models
uv run antenna-placement train

# 4. Scan Libya for coverage gaps and rank top placement recommendations
uv run antenna-placement recommend

# 5. Generate interactive Leaflet map
uv run antenna-placement map

# Or run the entire end-to-end pipeline in one step:
uv run antenna-placement all
```

### 3. Evaluate a Custom Candidate Location

To assess placement suitability, population demand, and recommended equipment for any custom GPS coordinate in Libya:

```bash
# Evaluate downtown Tripoli
uv run antenna-placement predict --lat 32.88 --lon 13.18

# Evaluate remote desert location (e.g. Murzuq)
uv run antenna-placement predict --lat 24.00 --lon 18.00
```

---

## 🏆 Top 5 High-Priority Recommended Deployments for Libya

| Rank | Municipality | Nearest Settlement | Suitability | Priority Score | Recommended Equipment Tier | 5km Population | Nearest Cell Gap |
| :---: | :--- | :--- | :---: | :---: | :--- | :---: | :---: |
| **#1** | **Zwara** | Aljmail | **0.847** | **7.43** | Suburban Standard Macro (B3 + B20) | 24,521 | 10.74 km |
| **#2** | **Zwara** | Al Ajaylat | **0.843** | **7.38** | Suburban Standard Macro (B3 + B20) | 24,013 | 14.83 km |
| **#3** | **Derna** | Alqubba | **0.927** | **7.37** | Suburban Standard Macro (B3 + B20) | 9,463 | 10.01 km |
| **#4** | **Benghazi** | Suloug | **0.896** | **7.17** | Suburban Standard Macro (B3 + B20) | 9,987 | 13.28 km |
| **#5** | **Benghazi** | Toukra | **0.791** | **7.01** | Urban High-Capacity Macro (B3+B1+B20) | 26,704 | 24.69 km |
