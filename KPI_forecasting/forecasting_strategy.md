# 4G/LTE KPI Forecasting Strategy

## Your Data at a Glance

| Property | Value |
|----------|-------|
| Time span | ~1 year (Sept 2025 - Sept 2026) |
| Granularity | Daily, per frequency band |
| Frequency bands | 6 (350, 400, 1556, 1700, 3500, 6200 MHz) |
| Total rows | 2,065 (~344 days x 6 bands) |
| KPIs available | 9 performance metrics + downtime counter |

---

## Part 1: What to Predict (and Why)

Not all KPIs are equally valuable to forecast. Here's a priority ranking based on **business impact** for a telecom operator:

### Tier 1 - High Business Impact (Predict These First)

#### 1. E-RAB Drop Rate
- **Why**: Directly impacts customer experience (dropped calls/sessions). A spike means users are getting disconnected mid-session.
- **Prediction goal**: Forecast next 7-14 days to trigger proactive alerts before degradation hits users.
- **Business value**: Early warning system for QoS violations and SLA breaches.

#### 2. 4G Cell Availability (%)
- **Why**: The single most important KPI for network operations. Predicting downtime windows lets you schedule maintenance and allocate field teams.
- **Prediction goal**: Forecast next 7-30 days to detect availability trends heading toward thresholds.
- **Business value**: Reduce unplanned outages, optimize maintenance scheduling.

#### 3. Avg RRC Connected Users
- **Why**: Traffic demand forecasting. Knowing how many users will connect helps with capacity planning.
- **Prediction goal**: Forecast next 30-90 days for capacity planning cycles.
- **Business value**: Right-size network resources, avoid congestion before it happens.

### Tier 2 - Operational Value

#### 4. E-UTRAN IP Throughput (DL & UL)
- **Why**: Throughput trends reveal capacity bottlenecks. Declining throughput with rising users = congestion signal.
- **Prediction goal**: Forecast next 30 days, correlate with user count predictions.
- **Business value**: Capacity expansion planning, bandwidth allocation.

#### 5. RRC Setup Success Rate & E-RAB Establishment Success Rate
- **Why**: Accessibility KPIs. If these drop, users can't even connect to the network.
- **Prediction goal**: Forecast next 7-14 days for anomaly detection.
- **Business value**: Early detection of hardware/software issues.

### Tier 3 - Supporting

#### 6. Handover Success Rates
- **Why**: Important for mobility, but less volatile day-to-day. Better suited for anomaly detection than forecasting.
- **Prediction goal**: Monitor for sudden drops rather than trend forecasting.

---

## Part 2: Recommended Algorithms

Ranked by how well they fit **your specific data** (1 year, daily, 6 bands, 9 KPIs).

---

### 1. XGBoost / LightGBM (Gradient Boosted Trees)

> [!TIP]
> **Best overall choice for your data.** Start here.

**Why it fits your data:**
- Works great with tabular data and engineered features (your calendar features, downtime flags, etc.)
- Handles the 6 frequency bands naturally as a feature
- Robust with ~2,000 rows (doesn't need massive data like deep learning)
- Fast to train, easy to tune, highly interpretable

**How to use it:**
- **Input features**: All your cleaned columns (lag features, rolling averages, calendar features, earfcndl, downtime flags)
- **Target**: Each KPI separately (one model per KPI)
- **Key trick**: Create **lag features** (value at t-1, t-7, t-14) and **rolling window stats** (7-day mean, 7-day std) - these are critical for time-series with tree models

**Feature engineering needed:**
```
For each KPI:
  - lag_1, lag_7, lag_14, lag_30    (past values)
  - rolling_mean_7, rolling_mean_14 (moving averages)
  - rolling_std_7                   (volatility)
  - diff_1, diff_7                  (rate of change)
```

**Expected performance**: Very strong for 7-14 day forecasts. Degrades for longer horizons.

**Libraries**: `xgboost`, `lightgbm`, `scikit-learn`

---

### 2. Prophet (Meta/Facebook)

> [!TIP]
> **Best for interpretability and quick wins.** Great second model.

**Why it fits your data:**
- Designed specifically for daily business time series (~1 year is enough)
- Automatically handles weekly and yearly seasonality
- Built-in handling of holidays and special events
- Produces confidence intervals (uncertainty quantification) out of the box
- Non-technical stakeholders can understand the decomposition plots

**How to use it:**
- **Input**: Just `Date` (ds) and the KPI value (y) - one model per (KPI, earfcndl band)
- **Regressors**: Add `Is_Weekend`, `pmCellDowntimeMan_log`, `Is_Cell_Down` as extra regressors
- Train 6 x N models (6 bands x N KPIs you want to forecast)

**Best for**: Cell Availability, User Count, Throughput (smooth, seasonal patterns)
**Weak for**: Drop Rate (spiky, event-driven - Prophet smooths too much)

**Libraries**: `prophet`

---

### 3. SARIMA / SARIMAX (Classical Statistics)

> [!IMPORTANT]
> **Best baseline model.** Every other model should beat this, or something is wrong.

**Why it fits your data:**
- The gold standard baseline for time-series forecasting
- SARIMA captures both trend and seasonality (weekly pattern in your KPIs)
- SARIMAX adds exogenous variables (your downtime features, weekend flag)
- Works well with 300+ daily observations per band

**How to use it:**
- One model per (KPI, earfcndl band)
- Use `auto_arima` from `pmdarima` to automatically find the best (p,d,q)(P,D,Q,s) parameters
- Set `s=7` for weekly seasonality

**Best for**: Establishing a performance floor. If XGBoost/Prophet can't beat SARIMA, your features aren't adding value.

**Libraries**: `statsmodels`, `pmdarima`

---

### 4. LSTM / GRU (Deep Learning)

> [!WARNING]
> **Use with caution.** Your dataset (~344 points per band) is on the small side for deep learning.

**Why it could work:**
- Can capture complex nonlinear temporal patterns
- Multivariate: can learn cross-KPI relationships (e.g., user count rise -> throughput drop)
- Can model all 6 bands together (shared patterns across frequencies)

**Why it's risky:**
- Needs more data to avoid overfitting (~344 daily points per band is thin)
- Harder to tune, slower to train, less interpretable
- Easy to get wrong (vanishing gradients, wrong sequence length, etc.)

**If you try it:**
- Use a simple architecture (1-2 LSTM layers, 32-64 units)
- Sequence length: 14-30 days lookback
- Heavy regularization (dropout 0.2-0.3)
- Train on ALL bands together (more data for the model)

**Libraries**: `tensorflow/keras`, `pytorch`

---

### 5. Transformer-based (N-BEATS, TFT, TimesFM)

> [!NOTE]
> **Future option.** Worth exploring once you have results from simpler models.

- Temporal Fusion Transformer (TFT): Handles multiple time series with static metadata (earfcndl band)
- N-BEATS: Pure time-series model, no feature engineering needed
- These need more data ideally, but can work with transfer learning

**Libraries**: `pytorch-forecasting`, `darts`, `neuralforecast`

---

## Part 3: Recommended Approach

### Multi-Model Strategy

Don't pick one algorithm. Use multiple and compare:

```
                    +------------------+
                    |   Data2_Cleaned  |
                    +--------+---------+
                             |
              +--------------+--------------+
              |              |              |
        +-----v----+  +-----v----+  +------v-----+
        |  SARIMA  |  | XGBoost  |  |  Prophet   |
        | (baseline)|  | (primary)|  | (secondary)|
        +-----+----+  +-----+----+  +------+-----+
              |              |              |
              +--------------+--------------+
                             |
                    +--------v---------+
                    |  Compare Metrics |
                    |  (MAE, RMSE,     |
                    |   MAPE, R2)      |
                    +--------+---------+
                             |
                    +--------v---------+
                    |  Best Model Per  |
                    |  KPI Per Band    |
                    +------------------+
```

> [!IMPORTANT]
> Different KPIs may have different best models. Drop Rate might be best with XGBoost while Availability might be best with Prophet. Don't force one model on everything.

---

## Part 4: Evaluation Strategy

### Train/Test Split for Time Series

> [!CAUTION]
> **NEVER** use random train/test split for time series. Always split chronologically.

```
|<-------- Training (80%) -------->|<-- Test (20%) -->|
Sept 2025                    June 2026            Sept 2026
```

### Metrics to Track

| Metric | What it tells you | Use when |
|--------|-------------------|----------|
| **MAE** (Mean Absolute Error) | Average magnitude of errors | General purpose, easy to interpret |
| **RMSE** (Root Mean Squared Error) | Penalizes large errors more | When big misses are costly |
| **MAPE** (Mean Absolute % Error) | Error as percentage | Comparing across KPIs with different scales |
| **R2** (R-squared) | How much variance explained | Overall model quality |

### Cross-Validation: Walk-Forward

For robust evaluation, use **expanding window** or **sliding window** cross-validation:

```
Fold 1: Train [Sept-Jan]  -> Test [Feb]
Fold 2: Train [Sept-Feb]  -> Test [Mar]
Fold 3: Train [Sept-Mar]  -> Test [Apr]
Fold 4: Train [Sept-Apr]  -> Test [May]
...
```

---

## Part 5: Implementation Roadmap

### Phase 1: Baseline (Start Here)
1. Build lag features + rolling stats on `Data2_Cleaned.csv`
2. Train SARIMA per (KPI, band) - this is your baseline to beat
3. Train XGBoost per KPI (all bands as feature)
4. Compare with MAE/RMSE

### Phase 2: Improve
5. Train Prophet per (KPI, band) with exogenous regressors
6. Ensemble: average predictions from top 2 models
7. Hyperparameter tuning (grid search or Optuna)

### Phase 3: Advanced (Optional)
8. Try LSTM if you want to capture cross-KPI dependencies
9. Try Temporal Fusion Transformer for multi-horizon forecasting
10. Build an anomaly detection layer on top of forecast residuals

---

## Part 6: What NOT to Do

| Mistake | Why it's bad |
|---------|-------------|
| Random train/test split | Leaks future information into training |
| One model for all KPIs | Different KPIs have different patterns |
| Ignoring earfcndl bands | 350 MHz and 3500 MHz behave very differently |
| Forecasting too far ahead | With 1 year of data, don't forecast beyond 30 days reliably |
| Skipping the baseline | Without SARIMA baseline, you can't prove your fancy model adds value |
| Over-engineering features | Start simple, add complexity only when metrics improve |
