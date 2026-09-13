# Loop Gain – AI Telecom Suite
### Samsung Innovation Campus (SIC) Capstone Project

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/badge/Package_Manager-uv-purple.svg)](https://github.com/astral-sh/uv)
[![AI/ML](https://img.shields.io/badge/Domain-Telecom_AI_Systems-orange.svg)](#)
[![Hardware](https://img.shields.io/badge/GPU_Accelerated-NVIDIA_CUDA-76B900.svg)](https://www.nvidia.com/)

An integrated suite of Artificial Intelligence systems engineered for telecommunications providers. Developed by **Team Loop Gain** as part of the **Samsung Innovation Campus (SIC) Capstone Project**, this platform addresses critical telecom operational challenges across customer retention, customer support automation, and infrastructure planning.

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

The repository is organized into three modular AI subsystems:

```
├── 1. customer_churn_prediction/     [✅ OPERATIONAL]
│   └── Customer Churn Prediction & Retention Discount Engine
│
├── 2. customer_support_chatbot/       [⏳ PLANNED]
│   └── Intelligent AI Customer Support Chatbot for Telecom Users
│
└── 3. antenna_cell_placement/         [✅ OPERATIONAL]
    └── Geospatial AI for Optimal Cellular Antenna Site Placement
```

---

## 🚀 Subsystems Overview

### 1. [Customer Churn Prediction & Retention Discount Engine](customer_churn_prediction/)
- **Status**: **Operational & Production Ready**
- **Objective**: Predicts customer churn risk with **0.9280 Test ROC-AUC** and **0.8561 PR-AUC** using CUDA-accelerated gradient boosting on NVIDIA GPUs.
- **Business Retention Engine**: Translates churn risk and account telemetry into margin-preserving marketing offers (`Offer A` through `Offer E`), contract lock-in agreements, and overage fee waivers, projecting **+$917,265.70** in net saved revenue.
- **Documentation**: See [`customer_churn_prediction/README.md`](customer_churn_prediction/README.md) and the comprehensive [`Technical Report`](customer_churn_prediction/TECHNICAL_REPORT.md).

### 2. [Telecom Customer Support AI Chatbot](customer_support_chatbot/)
- **Status**: **Planned / In Development**
- **Objective**: A conversational AI assistant designed for telecommunications subscribers to query package details, troubleshoot connectivity, resolve billing questions, and receive personalized promotional offers.

### 3. [AI Antenna Cell Site Placement Optimization](antenna_cell_placement/)
- **Status**: **Operational & Production Ready**
- **Objective**: Geospatial machine learning system predicting optimal geographic locations for deploying new cellular antenna towers across Libya with **0.9862 ROC-AUC** and **0.9794 PR-AUC**.
- **Geospatial & Demographic Intelligence**: Fuses crowdsourced cellular radio telemetry with WorldPop 1km gridded population density, SRTM 250m Digital Elevation Model (topography/prominence), UN OCHA road transportation networks, and Libyan administrative boundaries.
- **Optimization Engine**: Identifies unserved coverage gaps, ranks the Top 50 prioritized new site deployments, and recommends equipment tiers (`Urban_HighCapacity_Macro`, `Suburban_Standard_Macro`, `Rural_Coverage_Macro`).
- **Documentation**: See [`antenna_cell_placement/README.md`](antenna_cell_placement/README.md).

---

## 📁 Repository Structure

```
LoopGain-Telecom-AI/
├── README.md                          # Master Project Documentation & Team Directory
├── .gitignore                         # Global exclusion rules
│
├── customer_churn_prediction/         # Module 1: Customer Churn & Retention Engine
│   ├── README.md                      # Detailed Churn Module Documentation
│   ├── pyproject.toml                 # uv Package Config & CLI entry points
│   ├── uv.lock                        # Deterministic dependency lockfile
│   ├── churn_datasets/                # Telecom datasets (Maven Telecom, IBM, Cell2Cell)
│   ├── models/                        # Serialized champion model artifacts
│   ├── eval_reports/                  # ROC, PR, and feature importance charts
│   └── src/customer_churn_prediction/ # Feature engineering, trainers & discount engine
│
├── customer_support_chatbot/          # Module 2: Telecom Customer Chatbot (Placeholder)
│   ├── README.md                      # Module Overview
│   └── src/customer_support_chatbot/  # Chatbot source package
│
└── antenna_cell_placement/            # Module 3: Antenna Placement AI (Placeholder)
    ├── README.md                      # Module Overview
    └── src/antenna_cell_placement/    # Placement optimization package
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

## 📜 License

Developed for the Samsung Innovation Campus (SIC) Capstone Project by Team Loop Gain.
