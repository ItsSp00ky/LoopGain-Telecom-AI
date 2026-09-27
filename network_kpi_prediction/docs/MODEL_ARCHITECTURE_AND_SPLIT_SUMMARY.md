# Model Architecture & Dataset Split Technical Summary

> **Samsung Innovation Campus (SIC) AI Capstone // Team Loop Gain**  
> Technical documentation of the chronological validation strategy, model tournament architectures, and performance baselines.

---

## 1. Dataset Splitting Strategy (Train / Validation / Test)

The platform implements a **Strict Chronological 3-Way Split** across all telemetry series to prevent future lookahead bias and eliminate data leakage:

* **Train Set (70%)**:
  * **Role**: Primary model fitting, parametric harmonic estimation, and baseline feature extraction.
  * **Verification**: Strictly precedes the validation split chronologically.
* **Validation Set (15%)**:
  * **Role**: Hyperparameter tuning, regularized $\alpha$ optimization, and competitive **Champion Model Selection**.
  * **Integrity**: Evaluates model generalization on unseen future days before final holdout testing.
* **Test Holdout Set (15%)**:
  * **Role**: Kept completely untouched during training and tuning for unbiased out-of-sample evaluation.
* **Leak-Free Assertion**:
  * Programmatic assertion:
    $$\text{Max}(\text{Train Date}) < \text{Min}(\text{Validation Date}) < \text{Min}(\text{Test Date})$$

---

## 2. Machine Learning Model Architectures

The subsystem consists of two specialized forecasting engines:

### A. 3GPP Rel-17 Cellular KPI Forecasting Engine (60 Series)
Covers **6 frequency bands** (350, 400, 1556, 1700, 3500, 6200 MHz) across **standardized 3GPP operational metrics** (Accessibility, Retainability, Mobility, Capacity, and Availability).

An automated tournament evaluates 3 candidate model families and dynamically selects the best champion for each series based on validation MASE:

1. **Damped Fourier Ridge Regression** (*Champion for 40.0% of series*):
   * **Harmonic Modeling**: Uses orthogonal annual ($k=1, 2, 3$) and weekly ($k=1, 2$) Fourier terms.
   * **Damped Trend**: Incorporates an asymptotically saturating trend:
     $$\text{Trend}(t) = \frac{1 - e^{-\phi \cdot (t / 365.25)}}{\phi}$$
     Preventing long-term polynomial divergence over 365-day horizons.
   * **Leak-Free Cross-Validation**: `StandardScaler` is wrapped inside a scikit-learn `Pipeline` evaluated via 5-fold `TimeSeriesSplit`.
   * **Best For**: Stationary harmonic metrics (e.g. Downlink/Uplink Throughput, Handover Success Rate).

2. **Hybrid Trend-Seasonal Decomposition** (*Champion for 20.0% of series*):
   * **Architecture**: Combines a parametric Fourier base model with a `HistGradientBoostingRegressor` trained strictly on stationary residuals in transformed space:
     $$r_{\text{trans}} = \text{Transform}(y) - \text{Transform}(y_{\text{base}})$$
   * **Best For**: Non-linear subscriber spikes, active user growth, and dynamic capacity shifts.

3. **Adaptive Seasonal Naive Baseline** (*Champion for 40.0% of series*):
   * **Architecture**: A 7-day adaptive lookback profile capturing recent operational levels (56-day rolling window).
   * **Role**: Benchmark fallback guaranteeing holdout skill ($MASE \le 1.0$) on highly stochastic or regime-shifting series.

#### Additional Engineering Highlights:
* **Target Transformations**: `log1p` / `expm1` normalizes zero-inflated and highly skewed distributions (downtime, throughput).
* **Physical Domain Bounds**: 100% enforcement of physical boundaries ($[0\%, 100\%]$ for rates, non-negative bounds for users and throughput).
* **Quantile Prediction Ribbons**: Uses **Quantile Loss Gradient Boosting** to estimate empirical, non-Gaussian 90% confidence bands ($p_{05}$ to $p_{95}$).
* **Boundary Anchoring**: Exponential decay fuses the forecast origin with the latest observed historical state, eliminating artificial day-1 step jumps.

---

### B. 4G Network Traffic Volume Forecasting Engine (30-Day Cone)
Focuses on macro-level accumulated network traffic volume (GB).

* **Champion Model**: **Tuned Random Forest / XGBoost Regressor** (benchmarked against Ridge Regression and Seasonal Naive $t-7$).
* **Outlier Sanitization**: Robust IQR seasonal residual anomaly detection ($|z| > 3.0$) with same-day-of-week neighboring imputation ($t-7, t+7$).
* **Engineered Features**:
  * Multi-week autoregressive lags (`lag_1, 2, 3, 7, 14, 21, 28`).
  * Rolling statistical windows (`rolling_mean_7, 14, 28` and `rolling_std_7, 14, 28`).
  * Relative momentum growth differences (`diff_1`, `diff_7`, `ratio_7_28`).
  * Cyclical calendar signals ($\sin / \cos$ of Day-of-Week and Day-of-Year).
  * All statistical features strictly computed on `shift(1)` to eliminate lookahead leakage.
* **Output**: 30-day forward recursive cone with 80% and 95% confidence intervals and automated 1.2M GB carrier capacity alert monitoring.

---

## 3. Performance Summary

| Pipeline Component | Key Evaluation Metrics | Status |
| :--- | :--- | :--- |
| **Cellular KPI Engine** | **90.0%** of series achieved $R^2_{\text{bench}} > 0$<br>Median Test WAPE: **6.73%**<br>Median Validation MASE: **0.740** | **Operational** (60 Series) |
| **Traffic Volume Engine** | Test WAPE: **~2.22%**<br>Test $R^2 = 0.51 - 0.62$<br>Capacity Headroom: **0% Breach** of 1.2M GB | **Operational** (30-Day Cone) |
| **Unit Test Suite** | **49 / 49 Tests Passed** (100% pass rate) | **Fully Verified** |
