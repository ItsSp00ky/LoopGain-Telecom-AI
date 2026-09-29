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

Four modules, each built independently, now run behind one Streamlit shell
(`platform_app/`) and are started together with one command
(`python3 run_platform.py`). See [`document/PLATFORM_STATUS.md`](document/PLATFORM_STATUS.md)
for exactly what's wired up versus still a standalone module.

```
├── antenna_cell_placement/    [✅ OPERATIONAL] GIS antenna site planning, own FastAPI (api.py)
├── network_kpi_prediction/    [✅ OPERATIONAL] Network KPI forecasting, own FastAPI (api.py)
├── prepaid_churn/             [✅ OPERATIONAL] Customer churn/retention, own FastAPI + Streamlit
├── assistants/                [✅ OPERATIONAL] Customer chatbot + employee copilot (call prepaid_churn's API)
├── traffic_steering_son/      [✅ OPERATIONAL] Congestion detection & mobility load balancing
└── platform_app/              [✅ NEW] Shared Streamlit shell landing on all of the above
```

> **Superseded, not deleted**: `customer_churn_prediction/`, `customer_support_chatbot/`
> and `kpi_prediction/` are earlier, unreviewed precursors to `prepaid_churn/`,
> `assistants/` and `network_kpi_prediction/` respectively (nothing in the platform
> imports them - verified by grep before writing this). They're kept in git history
> rather than removed in this pass; ask before relying on anything inside them.

---

## 🚀 Subsystems Overview

### 1. [GIS Antenna Site Planning](antenna_cell_placement/)
- **Status**: **Operational**, explainable scoring (not black-box ML) is the default and requires no ML dependencies.
- **Objective**: Explainable priority scoring over corrected terrain, population, road and rooftop features for new cell site candidates in Libya, with a source-integrity check before every run (`antenna-placement doctor`).
- **API**: `antenna_cell_placement/src/antenna_cell_placement/api.py` — `/health`, `/shortlist`, `/rooftops`, `/map`, `/assess`.
- **Documentation**: See [`antenna_cell_placement/document/`](antenna_cell_placement/document/), especially `INTEGRATED_PLANNING.md`.

### 2. [Network KPI Forecasting](network_kpi_prediction/)
- **Status**: **Operational** for 4G traffic volume forecasting; two further pipelines (`cellular_kpi_forecast/`, `erbs_node_analytics/`) ship in this module but are not yet wired to the platform API.
- **Objective**: Chronological (not random) train/val/test split, a real multi-model benchmark (Ridge, Random Forest, XGBoost, seasonal-naive baseline), and a forecast with 80%/95% intervals from the retrained champion.
- **API**: `network_kpi_prediction/api.py` — `/health`, `/traffic/{horizon_days}day`.

### 3. [Customer Churn & Retention](prepaid_churn/)
- **Status**: **Operational**, the only module with its own pre-existing FastAPI + Streamlit + key-protected access control.
- **Objective**: Prepaid subscriber churn risk, value tiers and named-reviewer-approved retention offers, in Libyan dinar.
- **Documentation**: See [`prepaid_churn/README.md`](prepaid_churn/README.md) and [`prepaid_churn/docs/`](prepaid_churn/docs/).

### 4. [Customer Chatbot & Employee Copilot](assistants/)
- **Status**: **Operational**, calls `prepaid_churn`'s API only; no language model sets an offer, a price or a limit.
- **Documentation**: See [`assistants/README.md`](assistants/README.md).

---

## 📁 Repository Structure

```
LoopGain-Telecom-AI/
├── README.md                    # This file
├── run_platform.py              # Starts every backend + the shared shell with one command
├── platform_app/                # Shared Streamlit shell (Home + GIS/KPI pages, links to churn/assistants)
├── antenna_cell_placement/      # GIS module: pipeline, api.py, document/ (INTEGRATED_PLANNING.md etc.)
├── network_kpi_prediction/      # KPI module: three pipelines, api.py wraps traffic_volume_forecast
├── prepaid_churn/                # Churn module: pipeline, its own api.py + app/, docs/
├── assistants/                   # Customer chatbot + employee copilot, call prepaid_churn's API
├── traffic_steering_son/         # Congestion detection & mobility load balancing
└── customer_churn_prediction/, customer_support_chatbot/, kpi_prediction/
                                   # Superseded precursors, kept in history, not part of the platform
```

Each module keeps its own `pyproject.toml`/`uv.lock` (or `requirements.txt` for
`network_kpi_prediction/`) and its own tests; see each module's own README for how to
work on it directly.

---

## ⚡ Run the platform

One command starts every backend and the shared shell:

```bash
python3 run_platform.py
```

This starts, each in its own process on its own port:

| Service | Port | Needs |
|---|---|---|
| GIS API | 8001 | nothing extra |
| KPI API | 8002 | nothing extra |
| Platform shell | 8510 | nothing extra — **open this one** |
| Churn API | 8000 | `PREPAID_CHURN_CHATBOT_KEY` + `PREPAID_CHURN_COPILOT_KEY` env vars |
| Churn demo app | 8501 | same as above |
| Customer chatbot | 8503 | same as above, plus its own `.env` (see `assistants/README.md`) |
| Employee copilot | 8502 | same as above |

Without the two churn keys set, the launcher still starts GIS, KPI and the shell and
prints which services it skipped — nothing crashes for their absence. Set the keys
(see [`assistants/README.md`](assistants/README.md)) to bring up the full seven-service
platform. Press Ctrl+C to stop everything the launcher started.

Working on one module only? Each module's own Quick Start still works standalone —
see [`antenna_cell_placement/README.md`](antenna_cell_placement/README.md),
[`network_kpi_prediction/README.md`](network_kpi_prediction/README.md) and
[`prepaid_churn/README.md`](prepaid_churn/README.md).

---

## 📜 License

Developed for the Samsung Innovation Campus (SIC) Capstone Project by Team Loop Gain.
