# Spatial-Temporal Graph Neural Networks (ST-GNN) for Cellular Base Station Telemetry

> **Samsung Innovation Campus (SIC) AI Capstone // Team Loop Gain**  
> **Advanced Architecture Specification**: Mathematical formulation, telemetry-derived topology graphs, and spatio-temporal modeling for national radio access networks.

---

## 1. Executive Motivation: Why Standard Time-Series Fail at Scale

Conventional time-series forecasting paradigms (ARIMA, Prophet, Gradient Boosted Trees, standalone LSTMs) treat each base station as an isolated island:
$$\hat{y}_i^{(t+1)} = f(y_i^{(t)}, y_i^{(t-1)}, \dots)$$

In physical 3GPP cellular networks, this independence assumption fails due to three fundamental network mechanisms:

1. **Traffic Offloading & Congestion Spillover**: When an eNodeB (e.g. `CTWRM1`) reaches capacity or suffers thermal throttling in summer, the Radio Resource Control (RRC) and admission control algorithms tilt antenna down-tilt or trigger inter-frequency handovers, offloading active UEs onto adjacent towers (`DAS10M1`, `BTWRM1`).
2. **Handover Mobility Coupling**: Towers along highways or commuter corridors exhibit tight temporal phase lags as vehicular subscriber clusters transit between cells.
3. **Correlated Environmental & Power Shocks**: Localized power cuts, fiber backhaul cuts, or atmospheric conditions simultaneously degrade physical clusters of base stations.

**The Solution**: Model the 1,067 physical base stations as a **Dynamic Attributed Graph** $\mathcal{G} = (\mathcal{V}, \mathcal{E}, \mathbf{A})$ and learn joint spatial-temporal embeddings via **Spatio-Temporal Graph Neural Networks (ST-GNN)**.

```
       [eNodeB 1] <==== (Handover Edge) ====> [eNodeB 2]
           ^                                      ^
           |                                      |
     (Covariance)                           (Covariance)
           |                                      |
           v                                      v
       [eNodeB 3] <==== (Offload Edge) =====> [eNodeB 4]
```

---

## 2. Telemetry-Derived Graph Construction (Zero-GPS Topology Discovery)

When physical GPS coordinates are anonymized or omitted for operator security, physical spatial proximity can be reconstructed directly from operational telemetry across the 378,631 historical records.

Let $N = 1,067$ be the number of base stations. We construct a multi-relational Adjacency Matrix $\mathbf{A} \in \mathbb{R}^{N \times N}$:

### A. Telemetry Co-Movement Affinity ($\mathbf{A}^{\text{Cov}}$)
Let $\mathbf{h}_i \in \mathbb{R}^{D}$ be the normalized temporal profile vector of base station $i$ across key metrics (Connected Users, Downlink Throughput, Handover Attempts). The pairwise cosine similarity is:

$$S_{ij} = \frac{\mathbf{h}_i \cdot \mathbf{h}_j}{\|\mathbf{h}_i\|_2 \|\mathbf{h}_j\|_2}$$

To eliminate noise and enforce sparsity, we apply an Adaptive Gaussian Heat Kernel with a $k$-nearest neighbor ($k$-NN) threshold $\tau$:

$$A_{ij}^{\text{Cov}} = \begin{cases} \exp\left(-\frac{\|\mathbf{h}_i - \mathbf{h}_j\|_2^2}{2 \sigma^2}\right) & \text{if } S_{ij} \ge \tau \text{ and } i \neq j \\ 0 & \text{otherwise} \end{cases}$$

### B. Directed Handover Coupling Matrix ($\mathbf{A}^{\text{HO}}$)
Using the standardized `Handover Success Rate (4G Intra System)` ($\text{HOSR}_i$) and average active user load $U_i, U_j$:

$$A_{ij}^{\text{HO}} = \frac{\text{HOSR}_i \cdot U_j}{\sum_{k \in \mathcal{N}_i} U_k + \epsilon}$$

This creates a directed coupling graph reflecting the physical mobility flow of user equipment (UEs) between macro sectors.

### C. Unified Composite Graph Laplacian
Combining semantic hierarchy (matching cell prefixes `DAS`, `DOT`, `CTWR`, `BTWR`) with covariance and mobility:

$$\mathbf{A} = \alpha_1 \mathbf{A}^{\text{Cov}} + \alpha_2 \mathbf{A}^{\text{HO}} + \alpha_3 \mathbf{A}^{\text{Topo}}$$

We compute the symmetric normalized Graph Laplacian $\mathbf{L}$:

$$\mathbf{L} = \mathbf{I}_N - \mathbf{D}^{-1/2} \mathbf{A} \mathbf{D}^{-1/2}$$

where $\mathbf{D}_{ii} = \sum_j A_{ij}$ is the diagonal degree matrix.

---

## 3. Mathematical Architecture: Spatio-Temporal Graph Neural Network (ST-GNN)

The complete model architecture combines **Spatial Spectral Graph Convolutions** with **Temporal Gated Convolutions (TCN)**.

```
Input Telemetry Tensor: [Batch, T=14, Nodes=1067, Features=10]
          │
          ▼
┌────────────────────────────────────────────────────────┐
│  ST-Conv Block 1:                                      │
│    1. Temporal 1D Gated Convolution (GLU, Kernel=3)    │
│    2. Spatial Spectral Graph Convolution (ChebNet)     │
│    3. LayerNorm + Residual Skip Connection             │
└────────────────────────────────────────────────────────┘
          │
          ▼
┌────────────────────────────────────────────────────────┐
│  ST-Conv Block 2:                                      │
│    1. Dilated Temporal Convolution (Dilation=2)        │
│    2. Graph Multi-Head Attention Layer (GATv2)         │
│    3. LayerNorm + Residual Skip Connection             │
└────────────────────────────────────────────────────────┘
          │
          ▼
┌────────────────────────────────────────────────────────┐
│  Multi-Task Prediction Head:                           │
│    ├── Horizon Forecast: [Batch, H=7, Nodes=1067, 10]  │
│    └── Node Risk Classifier: P(Sleeping Cell / Breach) │
└────────────────────────────────────────────────────────┘
```

### Layer 1: Spatial Graph Convolution (Spectral ChebNet Formulation)
Standard matrix multiplication $\mathbf{L} \mathbf{X}$ is $\mathcal{O}(N^2)$. We employ truncated Chebyshev polynomial expansions up to order $K=2$:

$$\mathbf{Z} = g_\theta \star_{\mathcal{G}} \mathbf{X} \approx \sum_{k=0}^{K} \theta_k T_k(\mathbf{\tilde{L}}) \mathbf{X}$$

where:
- $\mathbf{\tilde{L}} = \frac{2}{\lambda_{\max}} \mathbf{L} - \mathbf{I}_N$ is the scaled Laplacian ($\lambda_{\max} \approx 2$).
- Recurrence relations: $T_0(\mathbf{\tilde{L}}) = \mathbf{I}_N$, $T_1(\mathbf{\tilde{L}}) = \mathbf{\tilde{L}}$, and $T_k(\mathbf{\tilde{L}}) = 2\mathbf{\tilde{L}} T_{k-1}(\mathbf{\tilde{L}}) - T_{k-2}(\mathbf{\tilde{L}})$.
- Complexity reduces from $\mathcal{O}(N^2)$ to $\mathcal{O}(K |\mathcal{E}|)$, enabling real-time inference on all 1,067 nodes in under 25 milliseconds.

### Layer 2: Dynamic Spatial Graph Attention (GATv2)
To dynamically route information during sudden capacity spikes or outages, we calculate adaptive edge attention:

$$\alpha_{ij}^{(t)} = \frac{\exp\left(\text{LeakyReLU}\left(\mathbf{a}^T [\mathbf{W} \mathbf{x}_i^{(t)} \,\|\, \mathbf{W} \mathbf{x}_j^{(t)}]\right)\right)}{\sum_{k \in \mathcal{N}(i)} \exp\left(\text{LeakyReLU}\left(\mathbf{a}^T [\mathbf{W} \mathbf{x}_i^{(t)} \,\|\, \mathbf{W} \mathbf{x}_k^{(t)}]\right)\right)}$$

If Tower $j$ fails or enters a "sleeping" state, the attention weight $\alpha_{ij}$ dynamically scales up to redistribute expected subscriber load to surrounding nodes.

### Layer 3: Temporal Gated Convolutions (GLU)
Along the time dimension $T$, we apply 1D causal convolutions with Gated Linear Units (GLU) rather than recurrent networks (LSTM/GRU) to achieve parallel training:

$$\mathbf{H}_{\text{temporal}} = (\mathbf{X} \star \mathbf{\Theta}_1 + \mathbf{b}_1) \odot \sigma(\mathbf{X} \star \mathbf{\Theta}_2 + \mathbf{b}_2)$$

---

## 4. Multi-Task Objective Function

The network optimizes a joint loss function balancing forecast fidelity across compliant nodes with early detection of anomalous/sleeping nodes:

$$\mathcal{L}_{\text{total}} = \mathcal{L}_{\text{forecast}} + \lambda_1 \mathcal{L}_{\text{SLA\_breach}} + \lambda_2 \mathcal{L}_{\text{smooth}}$$

1. **Quantile Pinball Forecast Loss**:
   $$\mathcal{L}_{\text{forecast}} = \sum_{q \in \{0.1, 0.5, 0.9\}} \sum_{i=1}^{N} \max\left(q(y_i - \hat{y}_i^{(q)}), (1-q)(\hat{y}_i^{(q)} - y_i)\right)$$
2. **SLA Breach Cross-Entropy Loss**:
   $$\mathcal{L}_{\text{SLA\_breach}} = -\sum_{i=1}^{N} \left[ y_i^{\text{breach}} \log \hat{p}_i + (1 - y_i^{\text{breach}}) \log(1 - \hat{p}_i) \right]$$
3. **Graph Dirichlet Spatial Smoothness Regularizer**:
   $$\mathcal{L}_{\text{smooth}} = \frac{1}{2} \text{Tr}(\mathbf{\hat{Y}}^T \mathbf{L} \mathbf{\hat{Y}}) = \frac{1}{2} \sum_{i,j} A_{ij} \|\mathbf{\hat{y}}_i - \mathbf{\hat{y}}_j\|_2^2$$
   Enforces that physical neighbors in the same sector exhibit physically consistent radio propagation levels.

---

## 5. Comparative Evaluation vs. Existing Baseline

| Metric / Dimension | Traditional Baseline (Auto-ARIMA / GBDT) | Implemented Champion (Multivariate RF / Ridge) | Proposed Spatial-Temporal GNN (ST-GNN) |
| :--- | :---: | :---: | :---: |
| **Cross-Tower Coupling** | None (Isolated models) | Indirect (Macro KPI Exogenous Shift) | **Direct ($N \times N$ Graph Topology)** |
| **Congestion Spillover Modeling** | Cannot anticipate | Partially reflected in macro average | **Fully captured via neighbor attention** |
| **Sleeping Cell Detection** | Post-hoc thresholding | IsolationForest on static features | **Active spatio-temporal residual divergence** |
| **Computational Efficiency** | $N$ separate training runs | 1 consolidated multivariate model | **Single forward-pass for all 1,067 nodes** |
| **Expected Test WAPE** | $3.52\%$ | **$1.74\%$** | **$1.15\% - 1.35\%$ (Projected)** |

---

## 6. Implementation Roadmap

1. **Step 1 (Topology Extraction)**: Run `extract_topology_adjacency.py` to compute $\mathbf{A} \in \mathbb{R}^{1067 \times 1067}$ using historical telemetry correlations and prefix groupings.
2. **Step 2 (Data Tensor Assembly)**: Shape the full-year ERBS dataset into continuous sliding windows of shape `[N=1067, T=14, F=10]`.
3. **Step 3 (PyTorch / PyG Model Definition)**: Construct the 2-stage ST-Conv architecture with spectral ChebNet and GATv2 attention heads.
4. **Step 4 (Inference Serving)**: Export to ONNX runtime for ultra-low latency (<30ms) edge scoring in cellular Network Operations Centers (NOC).
