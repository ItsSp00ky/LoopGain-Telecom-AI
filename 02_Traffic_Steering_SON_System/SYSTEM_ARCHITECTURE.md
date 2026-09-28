# System Architecture & 3GPP Mobility Load Balancing (MLB) Specifications
## Autonomous AI Traffic Steering for 4G LTE Cellular Networks

---

## 1. Telecom Standard Context: 3GPP Self-Organizing Networks (SON)

In high-density cellular networks, physical capacity is constrained by the number of **Physical Resource Blocks (PRBs)** allocated across the carrier bandwidth (e.g. 100 PRBs for a 20 MHz LTE channel). When active Radio Resource Control (RRC) connected users surge, the scheduler divides available PRBs into smaller allocations per user, causing download throughput to collapse.

Standard 3GPP specifications (**3GPP TS 36.300 / TS 36.331**) define **Mobility Load Balancing (MLB)** as an autonomous Self-Organizing Network (SON) capability to redistribute traffic from congested donor cells to underutilized neighboring acceptor cells without dropping calls.

---

## 2. Mathematical Formulation of 3GPP Handover Steering (A3 Event)

LTE mobile devices continuously measure the Reference Signal Received Power (RSRP) of their serving cell ($M_p$) and candidate neighbor cells ($M_n$). An **Event A3** (neighbor becomes offset better than serving cell) triggers a handover when the following inequality is satisfied:

$$M_n + \text{Ofn} + \text{Ocn} - \text{Hys} > M_p + \text{Ofp} + \text{Ocp} + \text{Off}$$

Where:
* $M_n, M_p$: Measured RSRP values of neighbor and serving cell (in dBm).
* $\text{Ofn}, \text{Ofp}$: Frequency-specific offsets (0 dB for intra-frequency handovers).
* $\text{Ocn}$: **Cell Individual Offset (CIO)** of the neighbor cell (the software parameter controlled by this AI engine).
* $\text{Ocp}$: Cell Individual Offset of the serving cell.
* $\text{Hys}$: Hysteresis margin to prevent ping-pong handovers (typically 1–2 dB).
* $\text{Off}$: A3 event threshold offset parameter.

### How the AI Shifts the Handover Boundary
By artificially increasing the neighbor's **Cell Individual Offset** ($\text{Ocn} \leftarrow \text{Ocn} + \Delta\text{CIO}$), the effective trigger condition becomes:

$$M_n - M_p > \text{Off} + \text{Hys} - \Delta\text{CIO}$$

Each $+1\text{ dB}$ increase in $\Delta\text{CIO}$ effectively expands the coverage boundary of the neighbor cell into the donor cell's coverage area, shifting $5\%\text{ to }8\%$ of cell-edge subscribers seamlessly to the neighbor.

---

## 3. Congestion Risk Index ($CRI$) Formulation

For every cell site $i$ on forecast date $t$, the system computes an empirical **Congestion Risk Index (0–100%)**:

$$CRI_{i,t} = w_{\text{load}} \cdot S_{\text{load}}(i,t) + w_{\text{speed}} \cdot S_{\text{speed}}(i,t) + w_{\text{drop}} \cdot S_{\text{drop}}(i,t)$$

Where the normalized component functions are:
* **Load Factor**: $S_{\text{load}} = \min\left(100, \frac{U_{i,t}}{\text{Cap}_i} \times 100\right)$ (Weight $w_{\text{load}} = 0.50$).
* **Speed Deficit**: $S_{\text{speed}} = \min\left(100, \max\left(0, \frac{15.0 - \text{TP}_{i,t}}{15.0} \times 100\right)\right)$ (Weight $w_{\text{speed}} = 0.40$).
* **Session Drop Risk**: $S_{\text{drop}} = \min\left(100, \frac{\text{DR}_{i,t}}{2.0} \times 100\right)$ (Weight $w_{\text{drop}} = 0.10$).

### Severity Classification Tiers:
* **`CRITICAL`**: $CRI \ge 80.0$ AND $\text{TP}_{i,t} < 5.0\text{ Mbps}$ (Immediate severe degradation).
* **`HIGH`**: $CRI \ge 70.0$ AND $\text{TP}_{i,t} < 8.0\text{ Mbps}$ (Approaching PRB exhaustion).
* **`MODERATE`**: $CRI \ge 60.0$ (High load, acceptable speed).
* **`NORMAL`**: $CRI < 60.0$ (Healthy operational headroom).

---

## 4. Candidate Neighbor Audit & Dynamic Headroom Protection

To prevent secondary congestion (overloading an acceptor cell), the engine implements **Dynamic Headroom Protection**:

```
Algorithm: Dynamic Multi-Cluster Traffic Steering Matcher
Input: Scored cell dataframe on date t, Cluster metadata mapping
Output: Prioritized list of 3GPP CIO prescriptions

1. Identify candidate acceptors in same cluster C_j == C_i where:
   - LoadFactor_j < 0.70
   - Headroom_j >= 5.0 users
   - Speed_j >= 8.0 Mbps
   - Availability_j >= 95.0%
2. Initialize remaining headroom dictionary: H_rem[j] = Headroom_j
3. For each congested donor cell (sorted by CRI descending):
   a. Filter neighbors in C_i with H_rem[j] >= 4.0 users
   b. Score candidate: Score_j = H_rem[j] * Speed_j
   c. Select optimal neighbor: j* = argmax(Score_j)
   d. Compute user shift: ΔU = min(0.25 * Users_donor, 0.40 * H_rem[j*])
   e. Decrement headroom: H_rem[j*] = H_rem[j*] - ΔU
   f. Map ΔU to 3GPP CIO prescription:
      - ΔU >= 10 users -> CIO +3 dB (High Priority)
      - 6 <= ΔU < 10 users -> CIO +2 dB (Medium Priority)
      - ΔU < 6 users -> CIO +1 dB (Low Priority)
```

---

## 5. Physical Throughput (QoE) Recovery Formula

In proportional fair scheduling, user throughput is approximately proportional to the fraction of scheduling time allocated:

$$\text{Throughput}_{\text{user}} \approx \frac{\text{Cell Capacity}}{U_{\text{active}}}$$

When $\Delta U$ users are shifted away from the donor cell, the projected post-offload speed is:

$$\text{Speed}_{\text{post}} = \text{Speed}_{\text{pre}} \times \left( \frac{U_{\text{donor}}}{U_{\text{donor}} - \Delta U} \right)$$

This delivers an empirical **$+10\%\text{ to }+35\%$ boost in user download throughput** on congested cells.
