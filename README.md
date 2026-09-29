# Loop Gain – AI Telecom Suite
### Samsung Innovation Campus (SIC) Capstone Project

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/badge/Package_Manager-uv-purple.svg)](https://github.com/astral-sh/uv)
[![AI/ML](https://img.shields.io/badge/Domain-Telecom_AI_Systems-orange.svg)](#)
[![Hardware](https://img.shields.io/badge/GPU_Accelerated-NVIDIA_CUDA-76B900.svg)](https://www.nvidia.com/)

An integrated suite of Artificial Intelligence systems engineered for telecommunications providers. Developed by **Team Loop Gain** as part of the **Samsung Innovation Campus (SIC) Capstone Project**, this platform addresses critical telecom operational challenges across customer retention, customer support automation, and infrastructure planning.

The active prepaid customer module is [`prepaid_churn/`](prepaid_churn/).
The `Ali_Branch` review delivery follows `tahaDev`; see [CODE_REVIEW.md](CODE_REVIEW.md) for implemented fixes, validation and the limitations of the historical subsystem claims below.

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

## 🌐 Platform Architecture

The repository is organized into four modular AI subsystems:

```
├── 1. customer_churn_prediction/     [✅ OPERATIONAL]
│   └── Customer Churn Prediction & Retention Discount Engine
│
├── 2. assistants/                     [✅ BUILT]
│   └── Customer Chatbot & Employee Copilot, grounded on the team's outputs
│
├── 3. antenna_cell_placement/         [✅ OPERATIONAL]
│   └── Geospatial AI for Optimal Cellular Antenna Site Placement
│
└── 4. network_kpi_prediction/         [✅ OPERATIONAL]
    └── 3GPP Rel-17 Cellular Telemetry & Network Traffic Forecasting Engine
```

---

## 🚀 Subsystems Overview

### 1. [Customer Churn Prediction & Retention Discount Engine](customer_churn_prediction/)
- **Status**: **Operational & Production Ready**
- **Objective**: Predicts customer churn risk with **0.9280 Test ROC-AUC** and **0.8561 PR-AUC** using CUDA-accelerated gradient boosting on NVIDIA GPUs.
- **Business Retention Engine**: Translates churn risk and account telemetry into margin-preserving marketing offers (`Offer A` through `Offer E`), contract lock-in agreements, and overage fee waivers, projecting **+$917,265.70** in net saved revenue.
- **Documentation**: See [`customer_churn_prediction/README.md`](customer_churn_prediction/README.md) and the comprehensive [`Technical Report`](customer_churn_prediction/TECHNICAL_REPORT.md).

### 2. [Customer Chatbot & Employee Copilot](assistants/)
- **Status**: **Customer chatbot and employee copilot built**
- **Objective**: Two assistants in one look. The customer chatbot answers which of the operator's packages fit a prepaid customer and whether the operator approved an offer for them; the employee copilot alerts on towers in trouble, answers about towers, the GIS shortlist and customers at risk with sources, and drafts work orders that only an employee can confirm.
- **Grounding**: The language model only picks a tool and phrases what came back; code checks every reply, so no price, offer or figure appears that a tool did not return.
- **Start it on your laptop**: [`assistants/TEAM_GUIDE.md`](assistants/TEAM_GUIDE.md), step by step for every team member.
- **Documentation**: See [`assistants/README.md`](assistants/README.md).

### 3. [AI Antenna Cell Site Placement Optimization](antenna_cell_placement/)
- **Status**: **Operational & Production Ready**
- **Objective**: Geospatial machine learning system predicting optimal geographic locations for deploying new cellular antenna towers across Libya with **0.9862 ROC-AUC** and **0.9794 PR-AUC**.
- **Geospatial & Demographic Intelligence**: Fuses crowdsourced cellular radio telemetry with WorldPop 1km gridded population density, SRTM 250m Digital Elevation Model (topography/prominence), UN OCHA road transportation networks, and Libyan administrative boundaries.
- **Optimization Engine**: Identifies unserved coverage gaps, ranks the Top 50 prioritized new site deployments, and recommends equipment tiers (`Urban_HighCapacity_Macro`, `Suburban_Standard_Macro`, `Rural_Coverage_Macro`).
- **Documentation**: See [`antenna_cell_placement/README.md`](antenna_cell_placement/README.md), the comprehensive [`Technical Report`](antenna_cell_placement/document/TECHNICAL_REPORT.md), and the [`Telecom GIS, RF & AI Planning Roadmap`](antenna_cell_placement/document/TELECOM_GIS_RF_AI_ROADMAP.md).

### 4. [Network KPI & Traffic Prediction Engine](network_kpi_prediction/)
- **Status**: **Operational & Production Ready**
- **Objective**: 3GPP Rel-17 NWDAF and O-RAN compliant multi-band cellular KPI and 4G data volume time-series forecasting engine with **90.0% holdout benchmark outperformance ($R^2_{bench} > 0$)**.
- **Multi-Band & KPI Scope**: 6 frequency tiers (350, 400, 1556, 1700, 3500, 6200 MHz) across 10 standardized 3GPP operational metrics (Accessibility, Retainability, Mobility, Capacity, Availability) plus 30-day network traffic volume projections.
- **S-Tier ML Architecture**: Damped Fourier harmonics, residual gradient boosting ensembles, real heteroscedastic quantile prediction intervals (p05–p95), exponential boundary anchoring, and 100% physical domain boundary enforcement.
- **Documentation**: See [`network_kpi_prediction/README.md`](network_kpi_prediction/README.md).

---

## 📁 Repository Structure

```
LoopGain-Telecom-AI/
├── README.md                          # Master Project Documentation & Team Directory
├── .gitignore                         # Global exclusion rules
│
├── customer_churn_prediction/         # Module 1: Customer Churn & Retention Engine
│   ├── README.md                      # Detailed Churn Module Documentation
│   ├── TECHNICAL_REPORT.md            # Churn Modeling & Value Engine Specification
│   ├── pyproject.toml                 # uv Package Config & CLI entry points
│   ├── uv.lock                        # Deterministic dependency lockfile
│   ├── churn_datasets/                # Telecom datasets (Maven Telecom, IBM, Cell2Cell)
│   ├── models/                        # Serialized champion model artifacts
│   ├── eval_reports/                  # ROC, PR, and feature importance charts
│   └── src/customer_churn_prediction/ # Feature engineering, trainers & discount engine
│
├── assistants/                        # Module 2: Customer Chatbot & Employee Copilot
│   ├── README.md                      # How to run them and what they may say
│   ├── chatbot_app.py                 # Customer chatbot (Streamlit)
│   └── src/assistants/                # Tool loop, reply checks, tools and shared look
│
├── antenna_cell_placement/            # Module 3: Antenna Placement AI
│   ├── README.md                      # Detailed Antenna Module Documentation
│   ├── TECHNICAL_REPORT.md            # Comprehensive Engineering & Decisioning Report
│   ├── TELECOM_GIS_RF_AI_ROADMAP.md   # Telecom GIS, RF & AI Planning Roadmap
│   ├── pyproject.toml                 # uv Package Config & CLI entry points
│   ├── uv.lock                        # Deterministic dependency lockfile
│   ├── Libyan_cells_dataset/          # Raw crowdsourced telecom datasets
│   ├── data/                          # Geospatial data (DEM, WorldPop, Roads, Admin, Radar)
│   ├── models/                        # Champion AI Models (LightGBM & RF)
│   ├── eval_reports/                  # Coverage maps, ROC curves & recommendations
│   └── src/antenna_cell_placement/    # Geospatial AI pipeline package
│
└── network_kpi_prediction/            # Module 4: Network KPI & Traffic Forecasting
    ├── README.md                      # Detailed Subsystem Documentation
    ├── main.py                        # Unified Subsystem CLI
    ├── requirements.txt               # Dependencies
    ├── kpi_prediction_pipeline/       # 3GPP Cellular Telemetry Pipeline (60 series)
    └── kpi_prediction_pipeline_traffic/ # 4G Traffic Volume Pipeline
```

---

## ⚡ Quick Start: Customer Churn System

To run the operational Customer Churn and Retention engine:

```bash
# Navigate to the churn module
cd customer_churn_prediction

# Sync dependencies using uv
uv sync

# Train the champion model using CUDA GPU acceleration:
uv run customer-churn-prediction train

# Evaluate model performance and generate visualization charts:
uv run customer-churn-prediction evaluate

# Score an individual customer and generate tailored retention offers:
uv run customer-churn-prediction recommend --customer-id 0004-TLHLJ

# Export full batch retention campaign targets to CSV:
uv run customer-churn-prediction batch-recommend --output retention_campaign_targets.csv
```

---

## 📡 Quick Start: Antenna Cell Placement AI

To run the geospatial cell placement optimization engine:

```bash
# Navigate to the antenna placement module
cd antenna_cell_placement

# Sync dependencies using uv
uv sync

# Run the end-to-end data cleaning, feature engineering, and model training:
uv run antenna-placement all

# Predict placement suitability and recommended equipment for any custom coordinate:
uv run antenna-placement predict --lat 32.88 --lon 13.18
```

---

## 📶 Quick Start: Network KPI & Traffic Prediction Engine

To run the 3GPP cellular and 4G traffic forecasting pipelines:

```bash
# Navigate to the network KPI prediction module
cd network_kpi_prediction

# Install dependencies
pip install -r requirements.txt

# Run all automated unit tests (48 tests, 100% pass rate)
python main.py test
python -m unittest discover -s kpi_prediction_pipeline_traffic/tests -p "test_*.py" -v

# Query real-time dynamic ML prediction with 90% confidence ribbons and SLA checks:
python main.py predict --carrier 3500 --kpi dl_throughput_mbps --days 7 --live

# Execute the 4G network traffic volume pipeline:
python main.py --pipeline traffic
```

---

## 📜 License

Developed for the Samsung Innovation Campus (SIC) Capstone Project by Team Loop Gain.
