# 4G/LTE Radio Node KPI Forecasting with XGBoost

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)
[![XGBoost](https://img.shields.io/badge/model-XGBoost-orange.svg)](https://xgboost.readthedocs.io/)
[![Scikit-Learn](https://img.shields.io/badge/toolkit-Scikit--Learn-F7931E.svg)](https://scikit-learn.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

An end-to-end Machine Learning and Time-Series Forecasting pipeline to predict critical 4G/LTE Radio Access Network (RAN) Key Performance Indicators (KPIs). Built with domain-aware feature engineering, frequency band isolation, and gradient-boosted decision trees.

---

## 📌 Table of Contents
- [📊 Overview & Objectives](#-overview--objectives)
- [🧠 Machine Learning Architecture & Algorithm Details](#-machine-learning-architecture--algorithm-details)
  - [Why XGBoost instead of Deep Neural Networks?](#why-xgboost-instead-of-deep-neural-networks)
  - [Activation Function vs. Objective Function](#activation-function-vs-objective-function)
  - [Mathematical Formulation of Splits & Leaf Weights](#mathematical-formulation-of-splits--leaf-weights)
- [⚙️ Hyperparameter Configuration](#️-hyperparameter-configuration)
- [🧹 Data Preprocessing & Cleaning Pipeline](#-data-preprocessing--cleaning-pipeline)
- [🛠️ Feature Engineering Architecture](#️-feature-engineering-architecture)
- [🏆 Model Performance & Evaluation Metrics](#-model-performance--evaluation-metrics)
- [📈 Visual Forecast Gallery](#-visual-forecast-gallery)
- [🔍 Learned Patterns & Feature Importances](#-learned-patterns--feature-importances)
- [🚀 Quick Start & Reproduction](#-quick-start--reproduction)
- [💾 Inference with Saved Models](#-inference-with-saved-models)
- [📁 Repository Structure](#-repository-structure)

---

## 📊 Overview & Objectives

In cellular telecommunications (4G/LTE RAN), Key Performance Indicators (KPIs) measure network health, user experience, and radio spectrum congestion. Forecasting these metrics enables telecom operators to **preempt customer churn**, **schedule maintenance during low-traffic windows**, and **optimize spectrum allocation**.

This project models and forecasts three critical Tier-1 KPIs across 6 distinct frequency bands (`earfcndl`):

1. **Avg RRC Connected Users** — Measures simultaneous active sessions on the radio cell (used for capacity planning and dimensioning).
2. **E-RAB Drop Rate (%)** — Percentage of established radio bearers abruptly terminated (primary metric for Quality of Service & voice/data drops).
3. **4G Cell Availability (%)** — Ratio of operational uptime against planned service hours (core SLA benchmark).

---

## 🧠 Machine Learning Architecture & Algorithm Details

### Why XGBoost instead of Deep Neural Networks?
For tabular time-series telemetry with ~2,000 daily observations across multi-carrier radio nodes, **XGBoost (eXtreme Gradient Boosting)** significantly outperforms classical ARIMA/SARIMA and deep recurrent neural networks (LSTM/GRU):
* **Tabular Inductive Bias:** Tree-based ensembles consistently outperform deep learning on tabular data without requiring massive billions-sample datasets.
* **Non-linear Multi-Feature Interactions:** Naturally captures non-linear relationships between radio metrics (e.g., handover failure rate vs. drop rate).
* **Robustness to Invariant Scaling:** Invariant to monotonic feature scaling, avoiding scale distortion.
* **Built-in Regularization:** Penalizes complex tree structures to avoid overfitting on noisy telemetry.

---

### Activation Function vs. Objective Function

> [!NOTE]
> **Activation Function Distinction:**
> In Deep Learning (Neural Networks), non-linear **activation functions** (e.g., *ReLU*, *GELU*, *Sigmoid*, *Tanh*) are applied element-wise at each hidden neuron to introduce non-linearity between affine transformations.
>
> In **Tree-Based Ensemble Models (XGBoost)**, individual decision trees partition the feature space with orthogonal hyperplanes. Therefore, **there is no activation function between layers**. Instead, non-linearity is achieved through hierarchical decision thresholds (splits), governed by the **Objective Function** and **Link Function**:

#### 1. Objective Function (Loss Function)
For continuous KPI regression, the model minimizes the regularized Mean Squared Error (MSE):
$$\mathcal{L}(\theta) = \sum_{i=1}^{n} l\left(y_i, \hat{y}_i\right) + \sum_{k=1}^{K} \Omega(f_k)$$
where the individual sample loss is:
$$l\left(y_i, \hat{y}_i\right) = \frac{1}{2} \left(y_i - \hat{y}_i\right)^2$$
and the tree complexity penalty $\Omega(f_k)$ is:
$$\Omega(f_k) = \gamma T + \frac{1}{2} \lambda \sum_{j=1}^{T} w_j^2 + \alpha \sum_{j=1}^{T} |w_j|$$
* $T$: Number of terminal leaf nodes.
* $w_j$: Output score/weight of leaf $j$.
* $\gamma$: Minimum loss reduction required to make a further partition.
* $\lambda$: $L_2$ regularization term (Ridge penalty).
* $\alpha$: $L_1$ regularization term (Lasso penalty).

#### 2. Link Function
Regression uses an **Identity Link**:
$$\hat{y}_i^{(t)} = \hat{y}_i^{(t-1)} + \eta f_t(x_i)$$
The final predicted KPI is simply the additive sum of the base score and the scaled shrinkage predictions of all trees.

---

### Mathematical Formulation of Splits & Leaf Weights

At each boosting round $t$, XGBoost approximates the objective using a **second-order Taylor expansion**:
$$\tilde{\mathcal{L}}^{(t)} \approx \sum_{i=1}^n \left[ g_i f_t(x_i) + \frac{1}{2} h_i f_t^2(x_i) \right] + \Omega(f_t)$$
Where the first derivative (**gradient**) and second derivative (**hessian**) for squared loss are:
$$g_i = \frac{\partial l(y_i, \hat{y}_i^{(t-1)})}{\partial \hat{y}_i^{(t-1)}} = \left(\hat{y}_i^{(t-1)} - y_i\right)$$
$$h_i = \frac{\partial^2 l(y_i, \hat{y}_i^{(t-1)})}{\partial (\hat{y}_i^{(t-1)})^2} = 1$$

#### Optimal Leaf Weight $w_j^*$
For a given tree structure with instance set $I_j$ at leaf $j$:
$$w_j^* = -\frac{\sum_{i \in I_j} g_i}{\sum_{i \in I_j} h_i + \lambda}$$

#### Split Finding Criterion (Gain)
When splitting a node into Left ($L$) and Right ($R$) subsets, the split gain is evaluated analytically:
$$\text{Gain} = \frac{1}{2} \left[ \frac{\left(\sum_{i \in I_L} g_i\right)^2}{\sum_{i \in I_L} h_i + \lambda} + \frac{\left(\sum_{i \in I_R} g_i\right)^2}{\sum_{i \in I_R} h_i + \lambda} - \frac{\left(\sum_{i \in I} g_i\right)^2}{\sum_{i \in I} h_i + \lambda} \right] - \gamma$$

---

## ⚙️ Hyperparameter Configuration

The hyperparameters were tuned specifically to balance model expressiveness against overfitting on volatile radio signals:

| Hyperparameter | Value | Role & Rationale |
|---|---|---|
| **`objective`** | `reg:squarederror` | Minimizes Mean Squared Error for continuous real-valued KPI values. |
| **`n_estimators`** | `500` | Maximum number of sequential boosting trees. |
| **`learning_rate` ($\eta$)** | `0.05` | Shrinkage step size; dampens each tree's weight to prevent aggressive overfitting. |
| **`max_depth`** | `6` | Maximum tree depth, allowing interaction terms up to $2^6 = 64$ leaf buckets. |
| **`subsample`** | `0.8` | Row subsampling: uses 80% of training data per tree (Stochastic Gradient Boosting). |
| **`colsample_bytree`** | `0.8` | Column subsampling: uses 80% random features per tree to decouple correlated KPIs. |
| **`min_child_weight`** | `3` | Minimum sum of instance Hessian required in a child node (filters small-sample noise). |
| **`reg_alpha` ($L_1$)** | `0.1` | Lasso penalty to enforce feature sparsity. |
| **`reg_lambda` ($L_2$)** | `1.0` | Ridge penalty to prevent extreme leaf prediction weights. |
| **`early_stopping_rounds`** | `30` | Halts training automatically when test validation error stops improving for 30 rounds. |
| **`random_state`** | `42` | Ensures deterministic, reproducible execution. |

---

## 🧹 Data Preprocessing & Cleaning Pipeline

1. **Deduplication:**
   * Exact duplicate rows removed.
   * Key collision deduplication on composite key `(Date, earfcndl)` to guarantee one observation per carrier frequency per day.
2. **Calendar & Regional Weekend Alignment:**
   * Telecom traffic patterns heavily depend on weekly business cycles.
   * Standard software libraries default to Saturday/Sunday weekends. The dataset was preprocessed to match the regional working calendar:
     * **Friday (Day 4) & Saturday (Day 5)** $\rightarrow$ **`Is_Weekend = 1`**
     * **Sunday through Thursday** $\rightarrow$ **`Is_Weekend = 0`** (Workdays)
3. **No Artificial Normalization Needed:**
   * Tree-based algorithms split data purely based on rank order ($\le$ or $>$).
   * Feature values remain in their original engineering units (e.g., Users, %, Mbps), preserving interpretability.

---

## 🛠️ Feature Engineering Architecture

Time-series features were created strictly **within each frequency band (`earfcndl`)** to avoid cross-frequency contamination:

```
Raw Daily Data (per band)
       │
       ├──► Lag Features:        [lag_1, lag_3, lag_7, lag_14]
       ├──► Rolling Averages:    [rolling_mean_7, rolling_mean_14]
       ├──► Volatility Metrics:  [rolling_std_7, rolling_std_14]
       ├──► Momentum Signals:    [diff_1 (daily change), diff_7 (weekly change)]
       └──► Calendar Signals:    [Day_of_Week, Is_Weekend, Month, Year]
```

* **Lag 1 & Lag 3:** Capture short-term inertia and the 2-day weekend transition.
* **Lag 7 & Lag 14:** Capture strong weekly circadian rhythm and bi-weekly trend patterns.
* **Rolling Mean 7 & 14:** Establish the rolling baseline of cell performance.
* **Rolling Std 7 & 14:** Quantify recent radio link volatility / instability.

---

## 🏆 Model Performance & Evaluation Metrics

### Validation Strategy: Chronological Split (No Lookahead Bias)
Time series data **must never be shuffled randomly**. We used a strict **70% chronological train / 30% test split**:
* **Training Period:** Sept 18, 2024 $\rightarrow$ May 22, 2025 (1,351 samples)
* **Test Evaluation Period:** May 23, 2025 $\rightarrow$ Sept 17, 2026 (579 samples across all 6 carriers)

### Evaluation Metrics Defined:
* **$R^2$ Score (Coefficient of Determination):** Proportion of variance explained by the model:
  $$R^2 = 1 - \frac{\sum (y_i - \hat{y}_i)^2}{\sum (y_i - \bar{y})^2}$$
* **MAE (Mean Absolute Error):** Average magnitude of errors in original KPI units:
  $$\text{MAE} = \frac{1}{n} \sum_{i=1}^n |y_i - \hat{y}_i|$$
* **RMSE (Root Mean Squared Error):** Penalizes large deviations/outliers:
  $$\text{RMSE} = \sqrt{\frac{1}{n} \sum_{i=1}^n (y_i - \hat{y}_i)^2}$$
* **MAPE (Mean Absolute Percentage Error):** Normalized relative error percentage:
  $$\text{MAPE} = \frac{100\%}{n} \sum_{i=1}^n \left| \frac{y_i - \hat{y}_i}{y_i} \right|$$

### Results Matrix

| KPI | $R^2$ Score | MAPE (%) | MAE | RMSE | Verdict |
|---|---|---|---|---|---|
| **Avg RRC Connected Users** | **0.9891** | **2.51%** | 0.4392 users | 0.9379 users | 🟢 Exceptional ($R^2 > 98\%$) |
| **E-RAB Drop Rate (%)** | **0.9795** | **6.51%** | 0.0217% | 0.0351% | 🟢 Exceptional ($R^2 > 97\%$) |
| **4G Cell Availability (%)** | 0.3441 | 4.69% | 3.9759% | 5.7742% | 🟡 Event-Driven Outages |

---

## 📈 Visual Forecast Gallery

### 1. E-RAB Drop Rate ($R^2 = 0.980$)
![Drop Rate Timeline](forecast_results/plots/forecast_E-RAB_Drop_Rate_timeline.png)

### 2. Avg RRC Connected Users ($R^2 = 0.989$)
![Users Timeline](forecast_results/plots/forecast_Avg_RRC_Connected_users_timeline.png)

*For the complete set of 12 charts including per-band breakdowns and weekly views, see [forecast_charts.md](forecast_charts.md).*

---

## 🔍 Learned Patterns & Feature Importances

Tree feature importances were computed using **fractional Gain** (the relative contribution of each feature to tree splits):

### 1. E-RAB Drop Rate Drivers:
1. `E-RAB Drop Rate_rolling_mean_14` (**50.57%**) — The 2-week rolling average is the dominant signal of underlying RF interference and network health.
2. `E-RAB Drop Rate_lag_1` (**11.45%**) — Immediate prior-day drop rate captures short-term persistent conditions.
3. `Year` (**9.13%**) — Macro long-term trend reflecting overall network growth.
4. `E-RAB Drop Rate_rolling_mean_7` (**7.33%**) — 1-week moving baseline.
5. `RRC Setup Success Rate` (**6.72%**) — Cross-KPI correlation with access success.

### 2. Avg RRC Connected Users Drivers:
1. `Avg RRC Connected users_lag_3` (**52.51%**) — Strongest cyclical pattern due to 3-day shift bridging weekend recovery.
2. `Avg RRC Connected users_lag_1` (**35.87%**) — Prior day's user volume.
3. `Avg RRC Connected users_rolling_mean_7` (**5.18%**) — 7-day average traffic baseline.

---

## 🚀 Quick Start & Reproduction

### 1. Clone & Setup
```bash
git clone https://github.com/<your-username>/KPI_forecasting.git
cd KPI_forecasting
pip install -r requirements.txt
```

### 2. Run Training Pipeline & Persist Models
```bash
python forecast_and_save_models.py
```
*Outputs evaluation metrics, feature importances, and serialized XGBoost model files in `forecast_results/`.*

### 3. Generate Evaluation Charts
```bash
python plot_forecasts.py
```
*Renders all 12 timeline, daily, weekly, and per-band evaluation plots in `forecast_results/plots/`.*

---

## 💾 Inference with Saved Models

Trained models are saved in standard XGBoost JSON format in `forecast_results/saved_models/`. You can load and use them in production without retraining:

```python
from forecast_and_save_models import load_saved_model
import pandas as pd

# Load the trained model and feature schema
model, features = load_saved_model("Avg RRC Connected users")

# Run inference on any new telemetry dataframe
# df_new = pd.read_csv("new_telemetry.csv")
# predictions = model.predict(df_new[features])
# print(predictions)
```

---

## 📁 Repository Structure

```text
├── README.md                          # Full architectural & technical documentation
├── requirements.txt                   # Environment dependencies (pinned versions)
├── .gitignore                         # Build and cache ignore patterns
├── Data2_Cleaned.csv                  # Preprocessed dataset (verified Fri/Sat weekend logic)
├── forecast_and_save_models.py        # End-to-end training and model persistence pipeline
├── plot_forecasts.py                  # Matplotlib script generating all 12 visual charts
├── forecasting_strategy.md            # Strategy guide on model selection and KPIs
├── forecast_charts.md                 # Markdown visual gallery of all forecast plots
└── forecast_results/
    ├── saved_models/                  # Serialized XGBoost models (.json) & schemas
    │   ├── model_E-RAB_Drop_Rate.json
    │   ├── model_Avg_RRC_Connected_users.json
    │   ├── model_4G_Cell_Av_pct.json
    │   ├── features_*.json
    │   └── model_metadata.json
    ├── plots/                         # 12 PNG evaluation charts
    ├── model_metrics.csv              # Benchmark metric table (R2, MAPE, MAE, RMSE)
    ├── feature_importances.json       # Top 10 feature weights per KPI
    └── predictions_*.csv              # Actual vs Predicted CSVs on 30% test set
```

---

## 📜 License
Distributed under the MIT License. See `LICENSE` for more information.
