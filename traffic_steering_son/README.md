# 🔄 4G LTE Autonomous Traffic Steering & Mobility Load Balancing (SON)

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![3GPP Standard](https://img.shields.io/badge/Standard-3GPP%20TS%2036.331-blueviolet.svg)](https://www.3gpp.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](#)

> Production-ready autonomous traffic steering and Self-Organizing Network (SON) engine for cellular telecommunications. Automatically detects impending cell tower congestion up to 109 days in advance and prescribes 3GPP-compliant handover offset actions (**Cell Individual Offset - CIO**) to offload traffic to underutilized neighboring cells.

---

## 🌟 Key Highlights

* **Predictive Congestion Mitigation**: Flags bottlenecks *before* they impact user experience by monitoring dynamic user capacity, throughput deficits, and call drop risks.
* **3GPP TS 36.331 Compliant**: Generates actionable software parameter adjustments (+1 dB, +2 dB, +3 dB CIO) compatible with Ericsson, Huawei, and Nokia RAN management systems.
* **Dynamic Headroom Protection**: Decrements available neighbor capacity in real time to avoid secondary bottleneck creation.
* **Quantifiable Quality of Experience (QoE) Gain**: Delivers an empirical **+10% to +35% download speed recovery** on congested donor sites.

---

## 📁 Repository Structure

```
02_Traffic_Steering_SON_System/
│
├── README.md                      # Project overview & quickstart
├── SYSTEM_ARCHITECTURE.md         # 3GPP standards, handover math & algorithms
├── RESULTS_AND_ACTIONS.md         # Prescriptions summary, cluster tables & plots
├── requirements.txt               # Dependencies
├── .gitignore                     # Git ignore rules
│
├── data/                          # Input forecasts and network metadata
│   ├── tower_level_forecast_predictions.csv
│   ├── tower_mapping.csv
│   └── Data_Cleaned.csv
│
├── src/                           # Modular production source code
│   ├── congestion_detector.py     # Multi-KPI Congestion Risk Index (CRI) engine
│   ├── mobility_load_balancer.py  # Dynamic multi-cluster neighbor offload matcher
│   └── run_traffic_steering.py    # End-to-end execution pipeline
│
├── outputs/                       # Actionable Output CSVs
│   ├── congestion_alerts_summary.csv        # 29,484 detected bottlenecks
│   ├── traffic_steering_recommendations.csv # 18,256 actionable 3GPP offload actions
│   └── cluster_capacity_breakdown.csv       # Regional capacity & headroom audit
│
└── assets/                        # High-resolution visual impact charts
    ├── visual_traffic_steering_qoe_impact.png
    ├── visual_cluster_capacity_headroom.png
    └── visual_daily_congestion_timeline.png
```

---

## 🚀 Quickstart & Installation

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/your-username/4g-lte-traffic-steering.git
cd 4g-lte-traffic-steering
pip install -r requirements.txt
```

### 2. Execute Traffic Steering Engine
```bash
python src/run_traffic_steering.py
```

### 3. Query Recommendations in Python
```python
import pandas as pd

# Load actionable recommendations
df = pd.read_csv("outputs/traffic_steering_recommendations.csv")

# Filter high-priority alerts for Tripoli (NT cluster)
high_prio_nt = df[(df['Cluster'] == 'NT') & (df['Priority'] == 'HIGH')]
print(high_prio_nt[['Date', 'Donor_Tower_Id', 'Acceptor_Tower_Id', 'Users_To_Offload', 'Recommended_3GPP_Action', 'Predicted_QoE_Boost']].head())
```

---

## 📊 Summary Prescriptions Overview

| Priority Level | 3GPP Parameter Adjustment | User Offload ($\Delta U$) | Total Actions | Projected QoE Boost |
| :--- | :--- | :---: | :---: | :---: |
| **High Priority** | Cell Individual Offset (CIO) **+3 dB** | $\ge 10$ users | **1,842** | **+25% to +40%** |
| **Medium Priority**| Cell Individual Offset (CIO) **+2 dB** | $6 - 9$ users | **6,419** | **+15% to +25%** |
| **Low Priority** | Cell Individual Offset (CIO) **+1 dB** | $3 - 5$ users | **9,995** | **+10% to +18%** |

For 3GPP handover trigger equations, dynamic headroom algorithms, and visual plots, consult:
* 📄 [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md)
* 📊 [RESULTS_AND_ACTIONS.md](RESULTS_AND_ACTIONS.md)
