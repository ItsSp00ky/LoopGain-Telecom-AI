# Machine Learning Model Architecture & Mathematical Foundations
## 4G LTE Cellular Network Operational KPI Forecasting

---

## 1. Mathematical Formulation of the Forecasting Models

The forecasting engine utilizes **Gradient Boosted Decision Trees (GBDT)** implemented via the **XGBoost Regressor** framework. GBDT was chosen over standard recurrent neural networks (RNNs/LSTMs) and ARIMA due to its proven superior performance on panel tabular time series with strong seasonal lags, multi-site heterogeneity, and non-linear interactions.

### 1.1. Regularized Objective Function
For a dataset of $n$ observations with $m$ features $\mathcal{D} = \{(x_i, y_i)\}$, the ensemble predicts the output at round $t$ through an additive expansion:

$$\hat{y}_i^{(t)} = \sum_{k=1}^t f_k(x_i) = \hat{y}_i^{(t-1)} + f_t(x_i)$$

Where $f_t \in \mathcal{F}$ represents an independent regression tree. The objective minimized at step $t$ is:

$$\mathcal{L}^{(t)} = \sum_{i=1}^n l\left(y_i, \hat{y}_i^{(t-1)} + f_t(x_i)\right) + \Omega(f_t)$$

Where:
* $l(y_i, \hat{y}_i)$ is the convex loss function.
* $\Omega(f_t)$ is the model complexity regularization penalty:

$$\Omega(f_t) = \gamma T + \frac{1}{2} \lambda \sum_{j=1}^T w_j^2$$

Where $T$ is the number of terminal leaves in tree $f_t$, $w_j$ is the continuous weight assigned to leaf $j$, $\gamma$ is the minimum loss reduction required to split, and $\lambda$ is the $L_2$ leaf regularization coefficient.

### 1.2. Loss Function & Optimization
The objective utilizes the **Mean Squared Error (MSE)** loss:

$$l(y_i, \hat{y}_i) = \frac{1}{2} (y_i - \hat{y}_i)^2$$

Using a second-order Taylor expansion approximation around the previous step prediction $\hat{y}_i^{(t-1)}$:

$$\tilde{\mathcal{L}}^{(t)} \approx \sum_{i=1}^n \left[ g_i f_t(x_i) + \frac{1}{2} h_i f_t^2(x_i) \right] + \gamma T + \frac{1}{2}\lambda \sum_{j=1}^T w_j^2$$

Where the first and second order analytical gradients are:
* First order gradient: $g_i = \partial_{\hat{y}^{(t-1)}} l(y_i, \hat{y}^{(t-1)}) = \hat{y}_i^{(t-1)} - y_i$
* Second order hessian: $h_i = \partial^2_{\hat{y}^{(t-1)}} l(y_i, \hat{y}^{(t-1)}) = 1.0$

### 1.3. Optimal Leaf Weights & Split Gain
For leaf node $j$ with sample instance index set $I_j = \{i \mid q(x_i) = j\}$, the optimal weight $w_j^*$ is analytically solved:

$$w_j^* = -\frac{\sum_{i \in I_j} g_i}{\sum_{i \in I_j} h_i + \lambda} = -\frac{\sum_{i \in I_j} (\hat{y}_i^{(t-1)} - y_i)}{|I_j| + \lambda}$$

When evaluating candidate splits into left ($I_L$) and right ($I_R$) partitions ($I = I_L \cup I_R$), the split criterion gain is:

$$\mathcal{G}_{\text{split}} = \frac{1}{2} \left[ \frac{(\sum_{i \in I_L} g_i)^2}{|I_L| + \lambda} + \frac{(\sum_{i \in I_R} g_i)^2}{|I_R| + \lambda} - \frac{(\sum_{i \in I} g_i)^2}{|I| + \lambda} \right] - \gamma$$

### 1.4. Histogram Binning Optimization (`tree_method='hist'`)
To train rapidly across 234,800 panel observations, continuous features are partitioned into discrete bins (default $256$ bins). Rather than sorting continuous values at every split ($O(n \log n)$), histograms of first and second gradients are constructed in $O(n)$, reducing split evaluation to $O(\#\text{bins})$.

---

## 2. Hyperparameter Specifications Across Models

All 4 target KPI models share identical structural hyperparameters, tuned to balance variance reduction and fast convergence:

| Hyperparameter | Value | Architectural Purpose |
| :--- | :---: | :--- |
| **`n_estimators`** | `350` | Total boosting iterations |
| **`max_depth`** | `6` | Maximum tree depth (prevents high-order overfitting) |
| **`learning_rate` ($\eta$)** | `0.07` | Shrinkage step size applied to leaf weights ($w \leftarrow \eta w$) |
| **`subsample`** | `0.80` | Row subsampling fraction per boosting round |
| **`colsample_bytree`**| `0.80` | Feature column subsampling per tree |
| **`tree_method`** | `'hist'` | Quantized histogram acceleration |
| **`random_state`** | `42` | Deterministic reproducibility seed |

---

## 3. Feature Engineering Formulations

Each model utilizes **23 leak-free predictive features** constructed without looking ahead into the target window:

### 3.1. Autoregressive Lag Operator
For site $s$ and date $t$, the lag operator $\mathcal{L}^k$ is defined as:

$$\mathcal{L}^k Y_{s,t} = Y_{s, t-k} \quad \text{for } k \in \{1, 2, 3, 7, 14, 21, 28\}$$

* $k=1$: Immediate prior-day performance (short-term autoregressive memory).
* $k=7$: Weekly seasonal lag (captures identical day-of-week dynamics).
* $k=14, 21, 28$: Multi-week macro trends.

### 3.2. Rolling Window Moving Statistics
Moving averages are strictly shifted backward by 1 day ($\text{shift}(1)$) so the target $Y_{s,t}$ is strictly excluded:

$$\mu_{s,t}^{(W)} = \frac{1}{W} \sum_{i=1}^W Y_{s, t-i} \quad \text{for } W \in \{7, 14, 28\}$$

$$\sigma_{s,t}^{(7)} = \sqrt{\frac{1}{7-1} \sum_{i=1}^7 \left( Y_{s, t-i} - \mu_{s,t}^{(7)} \right)^2}$$

### 3.3. Cyclical Calendar Encodings
To preserve the continuous periodic topology of time (e.g., Saturday follows Friday; December transitions into January), calendar variables are projected onto orthogonal trigonometric dimensions:

$$\text{sin\_dow} = \sin\left(\frac{2\pi \cdot \text{DOW}}{7}\right), \quad \text{cos\_dow} = \cos\left(\frac{2\pi \cdot \text{DOW}}{7}\right)$$

$$\text{sin\_month} = \sin\left(\frac{2\pi \cdot \text{Month}}{12}\right), \quad \text{cos\_month} = \cos\left(\frac{2\pi \cdot \text{Month}}{12}\right)$$

### 3.4. Cultural Calendar Flag
* **`is_libya_weekend`**: Binary indicator where Friday (index 4) and Saturday (index 5) evaluate to 1, representing the official Islamic weekend in Libya where commercial traffic shifts to residential towers.

### 3.5. Out-of-Fold Site Baselines
To inform the tree of each base station's physical capacity ceiling without target leakage:

$$\text{SiteMean}_s = \frac{1}{|T_{\text{train}}|} \sum_{t \in T_{\text{train}}} Y_{s,t}$$

This is computed exclusively on the 70% historical training partition.

---

## 4. Chronological Validation & Leakage Prevention Protocol

```
Historical Timeline (363 Days Total):
├── [2025-09-20] ── 70% Chronological Training Window ── [2026-06-02] ──┤── [2026-06-03] ── 30% Out-of-Time Test Horizon ── [2026-09-19] ──┤
│                  (254 Days / 234,800 Samples)                        │                 (109 Days / 114,233 Samples)                      │
```

* **No Random K-Fold**: Random cross-validation randomly shuffles past and future observations, causing catastrophic temporal leakage.
* **Warmup Masking**: The initial 28 days of the training window are used solely to populate $\mathcal{L}^{28}$ and $\mu^{(28)}$ without training updates, ensuring every row used in gradient boosting contains complete, un-imputed lag vectors.
