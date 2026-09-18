# AI Customer Value Management (CVM) Suite
### Capstone Project Proposal — Samsung Innovation Campus (Libya AI 2026)

| Field | Detail |
|---|---|
| **Project Title** | AI Customer Value Management Suite for Prepaid-Dominant Telecom Markets |
| **Reference Market** | Libya — Libyana (MCC/MNC 606-00) and Almadar Aljadid (606-01), both under LPTIC |
| **Team** | 6 engineering students |
| **Duration** | 3 weeks (15 working days) |
| **Infrastructure** | CPU-only core; free-tier GPU for two modules. Total budget ≤ $40 |
| **Curriculum Coverage** | Chapters 1, 5, 6, 7, 8, 9, 10 (see Appendix B) |
| **Version** | v2.0 — restructured for full syllabus alignment |

---

## 1. Executive Summary & Problem Statement

### 1.1 Executive Summary

Libya's mobile market is served principally by Libyana and Almadar Aljadid, both state-owned through LPTIC. The market is overwhelmingly **prepaid**, which means the operator has no contract, no billing relationship, and no cancellation event to observe. A customer does not leave. They simply stop topping up, and revenue disappears from the base without a single event being logged.

The **AI CVM Suite** is a decision-intelligence layer over data the operator already produces — CDRs, recharge logs, bundle purchases, cell KPIs, care tickets — that produces four operator-grade outputs per subscriber:

1. A calibrated **silent-churn probability** and an estimated time-to-churn window.
2. A **value and loyalty tier** from a prepaid-adapted RFM model plus predicted lifetime value.
3. A **dynamically priced offer**, loyalty-weighted and margin-constrained, including off-peak capacity offers that cost the network almost nothing.
4. A **personalised airtime advance limit**, replacing the static eligibility gate the operator uses today.

All four are reachable through an API, a campaign console, an Arabic subscriber-channel simulator, and a natural-language **CVM Copilot** built on a LangChain agent over the feature store.

The system runs end-to-end in Docker on a student laptop. Two modules use a free-tier GPU. Nothing in the design requires production hardware.

### 1.2 The Business Pain Points

Six structural failures, each an addressable engineering problem.

**P1 — Silent churn is invisible until it is irreversible.**
In postpaid markets churn is a signed cancellation. Here it is an absence: no top-up for 30, then 60, then 90 days, followed by number recycling. By the time a monthly report shows ARPU decline, the subscriber's social graph has already migrated to the competing SIM. There is no event to react to, only a decaying signal nobody watches per-subscriber.

**P2 — Dual-SIM share-of-wallet leakage.**
Carrying both a Libyana and an Almadar SIM is normal, driven by patchy coverage and on-net pricing. "Active" therefore misleads. A subscriber can stay technically active while 80% of their spend has moved. Conventional churn models score them as retained; in revenue terms they are half-lost. The leading indicator is measurable and currently unmeasured: **incoming-call volume holding steady while outgoing volume and off-net share both rise.** That subscriber has quietly made this their *receiving* SIM.

**P3 — A flat, undifferentiated bundle catalogue.**
The same handful of USSD bundles goes to a university student in Tripoli, a shop owner in Misrata, and a farmer in Sabha. Price is set uniformly in a spreadsheet and changed quarterly at best. A nine-year customer and a SIM activated last week see identical offers.

**P4 — Blanket promotions destroy margin.**
Mass "double credit" campaigns are the default retention instrument and are indiscriminate. A large share of the discount lands on customers who would have recharged anyway; another share lands on customers already gone. Net margin impact is never isolated because there is no holdout group.

**P5 — Network quality and churn are managed in separate buildings.**
Power instability, generator fuel supply, and fibre cuts produce localised degradation. The NOC sees a cell KPI. Marketing sees an ARPU dip. Nobody joins them, so the operator cannot answer the most valuable question in capex planning: *which cell sites cost us the most revenue in churn, and what is that worth in LYD?*

**P6 — The existing airtime advance is a static gate, and it manufactures churn.**

This is the sharpest finding in the project, and it comes from the operator's own published documentation rather than from assumption.

Libyana already operates a **Credit Loan** service. Per their public FAQ:

- The service is **free** and **activates automatically** for subscribers meeting the conditions.
- The qualifying condition is that the line has been **active on the network for 12 months** from purchase date.
- Settlement has a **7-day grace period**, via recharge card or credit transfer.
- If the debt is not cleared in that window, the number moves to a **"recharge stage"** permitting incoming calls only.
- If the debt is never settled, **the line is reset and put up for resale.**
- There is no cap on repeat borrowing provided the previous loan is fully settled.
- Access is via `*61121#` or the MyLibyana app.

Two consequences follow directly.

First, **the eligibility rule is a single binary threshold**. Twelve months of tenure, yes or no. A nine-year subscriber spending 60 LYD a month is treated identically to a thirteen-month sporadic one. There is no differentiation by risk, by value, or by loyalty beyond that one gate.

Second, and more seriously: **the retention product is also a churn mechanism.** Advance too much to the wrong subscriber, they cannot clear it inside seven days, the line degrades to incoming-only, and eventually the number is reset and resold. That is hard, irreversible churn, and the operator caused it. A static limit guarantees this happens to some subscribers every month.

The same FAQ also gives us something valuable: a **clean supervised label with a natural horizon**. Repaid within 7 days, yes or no. No synthetic guesswork required in the target definition.

### 1.3 Core Value Proposition

> **The AI CVM Suite converts passive prepaid telemetry into a per-subscriber, margin-constrained retention decision — daily, automatically, and with a defensible LYD figure attached to every action.**

This is deliberately **not a churn prediction project**. A churn score is an input, not a product. The system closes the loop:

```
predict who is leaking → quantify what they are worth → decide what to offer
  → price it within margin, loyalty and credit guardrails → deliver it in Arabic
  → hold out a control group → measure realised uplift → retrain
```

Five design principles separate it from a standard classroom churn notebook:

| Principle | In practice |
|---|---|
| **Calibrated, not ranked** | Pricing consumes probabilities as monetary expectations, so a 0.31 must mean 31%. All classifiers are probability-calibrated and scored on Brier and PR-AUC, never accuracy. |
| **Uplift, not propensity** | Budget goes only to *persuadables*. Never to sure things, never to lost causes. |
| **Value-add before discount** | Loyalty is rewarded with off-peak data, which costs the network almost nothing at 03:00, in preference to headline price cuts that permanently erode ARPU and are trivially matched. |
| **Credit that protects, not traps** | The advance limit is capped by repayment probability and lifetime value, with cooling-off periods and chronic-distress exclusion, because a mis-set limit destroys the line. |
| **Localised by construction** | Target definition, feature set, geography, offer copy and UI language encode Libyan prepaid reality rather than adapting a US postpaid dataset. |

### 1.4 Module Scope

Seven modules. Each is owned by one student and each maps to specific syllabus chapters.

| # | Module | Question it answers | Chapters | Owner |
|---|---|---|---|---|
| **M1** | **Silent Churn Engine** — LightGBM vs LSTM benchmark | Who stops generating revenue in 30 days, and *when*? | 5, 8, 9 | E2 |
| **M2** | **Value & Loyalty Tiering** — RFM-LE, clustering, PCA, CLV | What is this subscriber worth, and how loyal? | 5, 6 | E3 |
| **M3** | **Dynamic Pricing & Off-Peak Offloading** | What price or bonus for *this* subscriber, within margin? | 5 | E4 |
| **M4** | **Smart Advance** — learned micro-credit limit | How much airtime can we safely advance, and to whom? | 5 | E2 / E4 |
| **M5** | **Network-Experience Fusion** — AutoEncoder anomaly detection | Which subscribers are at risk from coverage, and which sites carry the most revenue-at-risk? | 9 | E3 |
| **M6** | **Arabic Care-Text Intelligence** — LoRA fine-tuned classifier | *Why* are subscribers unhappy, in their own words? | 7, 10 | E6 |
| **M7** | **CVM Copilot** — LangChain / RAG agent | Can a non-technical analyst query all of this in plain language? | 10 | E5 |

**Cut from v1 and why:** the ALS matrix-factorisation recommender (wrong tool for a catalogue of ten bundles; a segment-and-content rule beats it), EconML heterogeneous treatment effects (replaced by a simple two-model uplift difference), the contextual bandit (no online environment to explore in), and the extended business-case model (reduced to one section and one slide).

---

## 2. Datasets & Data Pipeline

### 2.1 Strategy: Real Structure, Generated Locality

No public Libyan CDR dataset exists, and none should — subscriber data cannot legally or ethically leave an operator. The project uses a hybrid corpus:

- **Real public datasets** supply the statistical structure of telecom behaviour: usage distributions, churn base rates, feature correlations, and genuine labels for validation.
- **A generative adversarial network** adds the Libyan prepaid layer: LYD recharge denominations, scratch-card channels, dual-SIM leakage, outage exposure, advance repayment.
- **Real Libyan geography** from OpenCelliD anchors the network layer to actual tower coordinates.

The report and the pitch state this plainly. Synthetic metrics are not evidence of production performance. The deliverable is a validated pipeline and decision logic with a deployment-ready schema.

### 2.2 Primary Datasets (publicly accessible, verified)

#### Dataset A — Iranian Churn Dataset (UCI ML Repository, ID 563) — PRIMARY

| Attribute | Value |
|---|---|
| Source | `archive.ics.uci.edu/dataset/563/iranian+churn+dataset` |
| Access | `from ucimlrepo import fetch_ucirepo; d = fetch_ucirepo(id=563)` |
| Size | 3,150 rows × 13 features + churn label |
| Licence | CC BY 4.0 |

Collected from an Iranian operator over 12 months. Features include call failures, complaints, subscription length, charge amount (ordinal 0–9), seconds of use, frequency of use, frequency of SMS, distinct called numbers, age group, tariff plan (pay-as-you-go vs contractual), status, a pre-computed *Customer Value* field, and the churn label. Attributes aggregate months 1–9; the label is customer state at month 12, with a 3-month planning gap.

**Why it anchors the project:** it is the closest public analogue on four axes at once. It is **prepaid**, it is **MENA-region**, it contains a **network-quality feature** (call failures) that most churn datasets omit, and its **9-month observation / 3-month prediction gap** is exactly the operational framing a real campaign needs.

Known quality issue: roughly 300 duplicate rows (~9.5%) requiring exact-match deduplication before use.

#### Dataset B — Cell2Cell (Duke University / Teradata CRM Center, via Kaggle) — SCALE & SEQUENCES

| Attribute | Value |
|---|---|
| Source | `kaggle.com/datasets/jpacse/datasets-for-churn-telecom` |
| Size | 71,047 instances × 58 features (51,048 labelled / 19,999 unlabelled holdout) |
| Class balance | ~29% churn in the labelled split |

Supplies volume and, critically, **trend and degradation features**: percent change in minutes of use, percent change in revenue, mean dropped voice calls, blocked calls, unanswered calls, care-call counts, handset attributes.

**Role:** this is where the team learns decay modelling. The `changem` / `changer` delta features are the direct ancestors of our `revenue_decay_ratio_7d_30d`. It is also large enough to make the **LSTM benchmark in M1 meaningful** — an LSTM on 3,000 rows would prove nothing. The unlabelled holdout serves as an inference load test.

#### Dataset C — IBM Telco Customer Churn (extended) — BENCHMARK & CLV

| Attribute | Value |
|---|---|
| Source | IBM Cognos community sample; mirrored on Kaggle |
| Size | 7,043 customers × ~19–33 features |
| Churn rate | ~27% |

The extended release includes **Churn Reason** (labelled categorical explanation), **CLTV** (benchmark lifetime-value target), and **Churn Score**.

**Role:** an independent CLTV benchmark for M2; a churn-reason taxonomy seeding M6's label set; and a small, fast dataset so the Week-1 baseline is never blocked on pipeline work.

#### Dataset D — OpenCelliD (geospatial)

| Attribute | Value |
|---|---|
| Source | `opencellid.org` (free API key; CC BY-SA) |
| Filter | MCC **606** (Libya); MNC **00** Libyana, **01** Almadar Aljadid |

Filtering to MCC 606 yields **real Libyan tower identifiers with coordinates**, used to assign each generated subscriber a genuine `home_cell_id` in a genuine district. The map in the demo shows authentic site positions, not invented ones.

#### Dataset E — Arabic text corpora for M6

Public Arabic sentiment and dialect corpora (ASTD, ArSAS, Arabic Reviews sets) provide pre-training signal for the care-ticket classifier, which is then adapted to a small hand-labelled set of synthetic telecom complaints in Libyan dialect. The label taxonomy is seeded from IBM's Churn Reason field: coverage, pricing, billing, speed, service, device.

### 2.3 Synthesis Engine — CTGAN (Chapter 9, Unit 3)

The public datasets have no concept of a scratch card, a zero-balance night, Ramadan, or a generator outage. We generate these conditionally on the real features so joint structure is preserved.

**This module is a direct application of Chapter 9 Unit 3 — Generative Adversarial Networks to create non-existent data.** CTGAN is a conditional tabular GAN: a generator proposes synthetic subscriber rows, a discriminator tries to separate them from real ones, and the two train adversarially until the generator wins. We are creating a non-existent population of Libyan subscribers, which is precisely the unit's stated objective applied to tabular rather than image data.

**Pipeline:**

1. **Adversarial fit** — CTGAN (primary) and TVAE (challenger) on the real corpus, with a Gaussian copula as the classical baseline. Comparing all three is itself a reportable experiment.
2. **Quantile mapping** — real monetary fields mapped onto the Libyan scale. Iranian `Charge Amount` (ordinal 0–9) maps by quantile onto the LYD scratch-card ladder, so a 90th-percentile spender lands on 50–100 LYD cards, not 5 LYD.
3. **Business-rule overlays** — constructs the real data cannot supply: outage exposure, Ramadan seasonality, public-sector salary-week recharge spikes, advance repayment behaviour.
4. **Explicit hazard function** for label generation, documented in the repository, so the model has recoverable signal and the evaluation is honest about being a simulation ground truth.
5. **Quality gate** (`SDMetrics`): KS-complement ≥ 0.85 on continuous marginals, pairwise correlation delta ≤ 0.10, and a **discriminator detection test** — a LightGBM classifier trained to separate real from synthetic should reach AUC ≤ 0.65. Above that, the generator is rejected and retrained.

That final gate is worth emphasising in the pitch: **we evaluate our GAN with an adversarial test, the same principle that trains it.**

### 2.4 Generated Field Specification

**Monetary / recharge dynamics**

| Field | Generation logic |
|---|---|
| `recharge_amount_lyd` | Multinomial over {5, 10, 15, 20, 25, 50, 100} LYD, weighted to low denominations, conditioned on value percentile |
| `recharge_channel` | {scratch_card, agent_erecharge, mylibyana_app, bank_card, p2p_transfer}, weighted to scratch/agent given low banking penetration |
| `recharge_count_30d` / `_90d` | Poisson, λ from mapped spend percentile |
| `days_since_last_topup` | Inter-arrival sampling. **The strongest single churn signal in prepaid** |
| `mean_inter_recharge_days` | Mean gap over 90d |
| `recharge_gap_cv` | Coefficient of variation of gaps — irregularity precedes exit |
| `balance_zero_hours_30d` | Hours at zero balance. No postpaid equivalent exists |
| `failed_bundle_attempts_30d` | Purchases rejected for insufficient balance — pure affordability signal |
| `credit_transfer_out_lyd` | Peer-to-peer credit sharing |

**Advance / credit dynamics (M4)**

| Field | Notes |
|---|---|
| `advance_taken_count_90d` | Historical use of the Credit Loan facility |
| `advance_amount_lyd` | Size of each advance |
| `advance_repaid_within_7d` | **Supervised label for M4**, matching the operator's real grace period |
| `days_to_settle` | Actual settlement lag, censored at 7 |
| `entered_recharge_stage_flag` | Line degraded to incoming-only after non-payment |
| `line_reset_flag` | Terminal outcome: number reset and resold. **Operator-caused hard churn** |
| `tenure_months_at_first_advance` | Reveals the existing 12-month gate in the data |

**Usage & leakage dynamics**

| Field | Why it matters locally |
|---|---|
| `data_mb_peak` / `data_mb_offpeak` | Night bundles drive major volume |
| `offpeak_data_ratio` | Identifies who can be rewarded with near-zero-cost night data |
| `voice_min_onnet` / `voice_min_offnet` | On-net pricing is the core competitive lever |
| `onnet_ratio` | **Dual-SIM leakage proxy** — falling on-net share means the social graph is migrating |
| `incoming_outgoing_ratio` | **Primary leakage detector** — rising incoming against flat outgoing means "this is my receiving SIM" |
| `distinct_called_numbers_trend` | Contraction of the calling graph precedes silent exit |
| `ussd_price_check_sessions_30d` | Repeated catalogue browsing indicates active price shopping |
| `social_bundle_share` | Share of data spend on social/messaging bundles |

**Network experience (joined to real OpenCelliD sites)**

| Field | Notes |
|---|---|
| `home_cell_id`, `home_lat`, `home_lon`, `district` | Real Libyan tower positions, MCC 606 |
| `cell_hourly_load_vector` | 24×30 matrix per cell. **Input to the M5 AutoEncoder and to off-peak trough detection** |
| `dropped_call_rate_30d` | Seeded from Iranian `Call Failures` and Cell2Cell `dropvce`, perturbed per cell |
| `data_session_failure_rate` | Per-cell, correlated with load |
| `cell_outage_hours_30d` | Power and fuel-driven exposure, higher in southern and peri-urban districts |

**Contextual, tenure, and text**

| Field | Notes |
|---|---|
| `tenure_months`, `consecutive_active_months` | Loyalty backbone, from `Subscription Length` |
| `ramadan_period_flag`, `summer_outage_index` | Seasonality overlays. Libyana publishes Ramadan, Hajj and student offers, confirming these cycles are real commercial events |
| `salary_week_flag` | Public-sector salary disbursement drives a pronounced recharge spike |
| `diaspora_roaming_flag` | Roaming events mark a high-value, low-churn segment |
| `care_ticket_text_ar` | Generated Arabic complaint text. **Input to M6** |
| `language_pref` | {ar, ar-LY, ber, en} — drives message rendering |
| `subscriber_id_hashed` | SHA-256 + salt. **No raw MSISDN exists anywhere in the repository** |

### 2.5 Feature Engineering & Prepaid-Adapted RFM

#### Redefining RFM for prepaid

Textbook RFM assumes purchase transactions. Prepaid has none, so each dimension is redefined and two are added.

| Dim | Standard | **Our prepaid definition** |
|---|---|---|
| **R — Recency** | Days since last purchase | Days since last **revenue-generating event** (top-up or bundle purchase). Usage alone does not count: a subscriber burning residual credit generates no revenue. |
| **F — Frequency** | Transaction count | Recharge count in 90d, **penalised by `recharge_gap_cv`**. Five regular recharges beat five erratic ones. |
| **M — Monetary** | Total spend | Total LYD in 90d, **plus the 30d-vs-prior-60d slope**, so decline is visible inside the score itself. |
| **L — Loyalty** | *(added)* | `0.4·tenure_scaled + 0.3·consecutive_active_months_scaled + 0.3·lifetime_recharge_percentile` |
| **E — Engagement** | *(added)* | Service breadth: distinct service types used (voice, SMS, data, bundles, transfers, advances), normalised. |

Quintile scoring 1–5 per dimension produces an `R|F|M|L|E` cell, collapsed into eight business segments: Champions, Loyal High-Value, Potential Loyalists, Promising New, Needs Attention, At-Risk Valuable, Hibernating, Lost.

#### Derived feature families

| Family | Representative features |
|---|---|
| **Velocity / decay** | `revenue_decay_ratio = mean_7d / mean_30d`, plus equivalents for data, voice, SMS. Values well below 1.0 are the earliest reliable tell |
| **Volatility** | Std-dev and CV of inter-recharge gaps; rolling variance of daily data usage |
| **Ratios & mix** | `onnet_ratio`, `offpeak_data_ratio`, `bundle_vs_payg_share`, `data_to_voice_ratio` |
| **Distress** | `balance_zero_hours`, `failed_bundle_attempts`, downgrades, consecutive sub-5-LYD recharges |
| **Leakage** | `incoming_outgoing_ratio` trend, off-net share trend, distinct-called-numbers contraction |
| **Credit** | Advance frequency, settlement lag, prior recharge-stage events |
| **Network exposure** | Outage-hours-weighted dropped-call rate over home cell and top-3 visited cells |
| **Sequence tensors** | Per-subscriber 90 × *k* daily matrices of recharge, data, voice, SMS. **Direct input to the M1 LSTM — no aggregation applied** |

#### Leakage controls (methodological)

All features are computed over an observation window ending strictly before the label window opens. Splits are **temporal, never random**. Any field used to generate the synthetic label is excluded from the feature matrix. An automated CI test enforces all three.

The last point matters commercially too: the Iranian dataset's pre-computed `Customer Value` field partially encodes the outcome, and dropping it is why our reported metrics are lower than published ones.

---

## 3. System Architecture & AI/ML Methodology

### 3.1 Data Flow Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│  LAYER 0 — SOURCES                                                       │
│  [UCI Iranian]  [Cell2Cell]  [IBM Telco]  [OpenCelliD]  [Arabic corpora] │
│    3,150 rows    71,047 rows   7,043 rows    MCC 606       ASTD/ArSAS    │
└───────────┬────────────┬────────────┬─────────────┬────────────┬─────────┘
            └────────────┴────────────┴─────────────┴────────────┘
                                  ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  LAYER 1 — INGESTION & LANDING                       (Python · PyArrow)  │
│  Pandera schema contracts · dedup (~300 UCI dups) · MSISDN → SHA-256     │
│  raw → Parquet, partitioned by snapshot_date                             │
└──────────────────────────────┬───────────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  LAYER 2 — GAN SYNTHESIS ENGINE                    ★ Ch 9 · Unit 3 ★     │
│                                                                          │
│   ┌───────────┐        generated rows        ┌───────────────┐           │
│   │ Generator │ ───────────────────────────► │ Discriminator │           │
│   └─────▲─────┘                              └───────┬───────┘           │
│         │            adversarial loss                │                   │
│         └────────────────────────────────────────────┘                   │
│              CTGAN (primary) · TVAE · Copula (baseline)                  │
│                               │                                          │
│                               ▼                                          │
│   quantile→LYD mapping  →  business overlays (outage, Ramadan, salary)   │
│                               │                                          │
│   [ QUALITY GATE: KS ≥ 0.85 · corr Δ ≤ 0.10 · detection AUC ≤ 0.65 ]     │
└──────────────────────────────┬───────────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  LAYER 3 — TRANSFORM & FEATURE STORE            (DuckDB · Polars)        │
│  rolling 7/30/90d aggregates · RFM-LE quintiles · decay & leakage ratios │
│  cell join via home_cell_id · per-cell 24×30 load matrices               │
│  ────────────────────────────────────────────────────────────────────    │
│  features_offline.parquet  (point-in-time correct, for training)         │
│  sequences_offline.npz     (90 × k daily tensors, for the LSTM)          │
│  features_online.duckdb    (serving + RAG retrieval, keyed by hash)      │
└──────────────────────────────┬───────────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  LAYER 4 — MODEL LAYER                                                   │
│                                                                          │
│  M1 CHURN — head-to-head benchmark              Ch 5 · Ch 8 · Ch 9       │
│    ┌────────────────────────┐   ┌────────────────────────┐               │
│    │ Arm A: LightGBM on     │vs │ Arm B: LSTM on raw     │               │
│    │ engineered features    │   │ daily sequences (Keras)│               │
│    └────────────────────────┘   └────────────────────────┘               │
│    + Cox PH survival → time-to-churn window                              │
│                                                                          │
│  M2 VALUE — RFM-LE rules ∥ K-Means ∥ Hierarchical ∥ PCA   Ch 6           │
│           + BG/NBD & Gamma-Gamma CLV                      Ch 5           │
│                                                                          │
│  M4 ADVANCE — repayment PD head (shares M1 features)      Ch 5           │
│                                                                          │
│  M5 NETWORK — AutoEncoder over cell load matrices         Ch 9           │
│    reconstruction error = degradation score                              │
│                                                                          │
│  M6 TEXT — Arabic transformer, LoRA fine-tuned            Ch 7 · Ch 10   │
│    care ticket → reason code + sentiment                                 │
│                                                                          │
│                     ▼                                                    │
│            [ MLflow Tracking ] ──► model_registry/                       │
└──────────────────────────────┬───────────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  LAYER 5 — DECISION ENGINE  ★ the commercial core ★        Ch 5          │
│                                                                          │
│  churn_prob ─┐                                                           │
│  time-to-churn│  ┌──────────────┐   ┌──────────────────┐                 │
│  CLV ─────────┤  │ Uplift filter│──►│ M3 Pricing:      │                 │
│  loyalty_idx ─┼─►│ persuadables │   │ discount / bonus │                 │
│  repay_PD ────┤  │ only         │   │ + off-peak offer │                 │
│  net_exposure┤  └──────────────┘   └────────┬─────────┘                 │
│  reason_code ┘                               │                           │
│                                              ▼                           │
│           ┌──────────────────────────────────────────────┐               │
│           │ GUARDRAILS: margin floor · CLV ceiling ·      │               │
│           │ budget LP · cannibalisation · credit safety · │               │
│           │ fairness audit · full decision log            │               │
│           └────────────────────┬─────────────────────────┘               │
│                                ▼                                         │
│   { offer_id, price_lyd, bonus_mb, valid_hours, advance_limit_lyd,       │
│     stage, reason_codes[], expected_margin_lyd }                         │
└──────────────────────────────┬───────────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  LAYER 6 — SERVING API                       (FastAPI · Pydantic v2)     │
│  /v1/score/churn   /v1/offer/next-best   /v1/price/quote                 │
│  /v1/advance/limit /v1/subscriber/{id}   /v1/network/site-risk           │
│  /v1/text/classify /v1/copilot/ask       /health  /docs                  │
│  target p95 < 200 ms for tabular endpoints, single CPU container         │
└────────┬──────────────────────┬───────────────────────┬──────────────────┘
         ▼                      ▼                       ▼
┌──────────────────┐  ┌───────────────────┐  ┌──────────────────────────┐
│ 7a CVM COMMAND   │  │ 7b CHANNEL SIM    │  │ 7c CVM COPILOT  ★Ch 10★  │
│ CENTER           │  │ USSD + SMS        │  │                          │
│ exec KPIs ·      │  │ Arabic RTL        │  │  analyst question (NL)   │
│ segments ·       │  │ *61121# advance   │  │        │                 │
│ subscriber 360 · │  │ menu mock         │  │        ▼                 │
│ campaign builder │  │ LLM-written copy  │  │  LangChain agent         │
│ · Libya risk map │  │                   │  │   ├─ DuckDB SQL tool     │
│ · complaint      │  │                   │  │   ├─ model API tool      │
│   reason cloud   │  │                   │  │   └─ RAG over docs/      │
│                  │  │                   │  │      model cards         │
│                  │  │                   │  │        ▼                 │
│                  │  │                   │  │  grounded answer + cohort│
└──────────────────┘  └───────────────────┘  └──────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  LAYER 8 — MLOps   Docker Compose · GitHub Actions · pytest · MLflow     │
│  Evidently drift · model cards · decision audit log · leakage test       │
└──────────────────────────────────────────────────────────────────────────┘
```

**Runtime footprint:** five containers (`api`, `ui`, `mlflow`, `duckdb-volume`, `copilot`), CPU-only at serving time, under 4 GB RAM. LSTM and LoRA training run separately on free-tier GPU and ship as saved artefacts.

### 3.2 Models and Their Roles

#### M1 — Silent Churn Engine: a genuine architecture benchmark

**Chapters 5, 8, 9.** This module is deliberately structured as an experiment rather than a single model, because the experiment is more informative than either arm alone.

**Arm A — LightGBM on engineered features** (Ch 5: Ensemble Algorithm)

| | |
|---|---|
| Algorithm | LightGBM primary; XGBoost and CatBoost challengers; Decision Tree and Logistic Regression as mandatory interpretable baselines (Ch 5 Units 3–4) |
| Input | ~80 engineered features from §2.5 |
| Tuning | Optuna, time-boxed to 50 trials (Ch 5 objective: hyperparameter tuning) |

**Arm B — LSTM on raw daily sequences** (Ch 8: build and train deep neural networks; Ch 9 Unit 2: RNN for sequential data)

| | |
|---|---|
| Architecture | Input `(90, k)` daily tensor → Masking → LSTM(64) → Dropout(0.3) → LSTM(32) → Dense(16, ReLU) → Dense(1, sigmoid) |
| Framework | TensorFlow / Keras |
| Regularisation | Dropout and early stopping, directly addressing the Ch 8 objective on preventing overfitting |
| Vanishing gradients | LSTM gating is itself the answer to the Ch 8 vanishing-gradient objective, and the report explains why a plain RNN fails on 90-step sequences |
| Input | Raw daily recharge, data, voice, SMS. **No hand aggregation** — the point is whether the network learns the decay patterns we engineered by hand |

**Shared framing for both arms:** 90-day observation → 15-day gap → 30-day outcome. Target is zero revenue-generating events for ≥ 30 consecutive days in the prediction window. Temporal split, never random. Class weighting first, with SMOTE/ADASYN as a documented comparison applied **inside** CV folds. Both arms are probability-calibrated with isotonic regression, because the pricing engine consumes probabilities as monetary expectations.

**Metrics:** PR-AUC (primary), lift @ decile 1–3, Brier score, ROC-AUC (secondary). **Accuracy is not reported** — it is meaningless at a 10–30% base rate.

**Why this benchmark is worth a slide.** Either outcome is a result. If the LSTM wins, sequential structure carries information our features discard, and we say so. If LightGBM wins, which is the likelier outcome on short sparse prepaid histories, we explain *why*: 90 timesteps of mostly-zero daily activity is a weak sequence signal, gradient boosting is extremely strong on tabular data, and the engineered decay ratios already encode most of the temporal information. Demonstrating an informed architecture choice is a stronger technical signal than defaulting to a neural network because it sounds advanced.

**Explainability:** SHAP TreeExplainer on Arm A, with per-subscriber waterfall plots surfaced in the UI. Arm B is compared on calibration and lift, not interpretability, and the gap is discussed.

**Reality check, stated in the report.** Published results on the Iranian dataset reach ~97% accuracy and ~0.99 AUC. Those figures are inflated by duplicate rows and by the pre-computed `Customer Value` field, which partially leaks the outcome. We deduplicate, drop the leaky field, split temporally, and report the resulting lower, honest metrics alongside the naive ones with the gap explained.

**M1b — Time-to-Churn.** `lifelines` Cox Proportional Hazards, with a Random Survival Forest challenger. Classification answers *if*; survival answers *when*. Retention economics are timing-sensitive: intervening 40 days early wastes budget, 5 days late wastes everything. The Cox output sets campaign trigger windows and **defines the stage boundaries of the retention ladder in §3.3**. Concordance index is the reported metric.

#### M2 — Value Segmentation & CLV

**Chapters 5 and 6.** Three unsupervised techniques applied in parallel, which is exactly the Chapter 6 unit structure.

- **K-Means** (Ch 6 Unit 3, non-hierarchical) on scaled RFM-LE, with *k* selected by silhouette and elbow.
- **Hierarchical clustering** (Ch 6 Unit 2) with a dendrogram, used as a structural cross-check and to decide whether the eight business segments are natural or imposed.
- **PCA** (Ch 6 Unit 4, linear factor model for dimensionality reduction) for 2-D segment visualisation and to check how much RFM-LE variance sits in two components.
- **Rule-based RFM-LE quintiles** as the business-legible reference. Where the rules and the clusters disagree, the disagreement is itself a dashboard insight.

**CLV:** `lifetimes` BG/NBD plus Gamma-Gamma, treating each **recharge as a transaction**. The non-contractual, alive-or-dead-unobserved assumption behind BG/NBD is literally true in prepaid, which makes this an unusually clean fit. Benchmarked against the IBM CLTV field.

**Role:** CLV is the **budget ceiling**. Hard rule: total retention spend on a subscriber never exceeds a configurable fraction of predicted 12-month CLV, default 15%. That single constraint is what makes the pricing engine defensible to a CFO.

#### M3 — Dynamic Pricing & Off-Peak Offloading

**Chapter 5.** Two mechanisms in one module.

**(a) Personalised price.** For bundle `b`, subscriber `i`:

```
P(i,b) = P_base(b) × ( 1 − d(i,b) )

d(i,b) = clip(
            w₁·ChurnRisk(i)                  ← urgency
          + w₂·LoyaltyIndex(i)               ← earned reward
          + w₃·PriceSensitivity(i,b)         ← elasticity
          − w₄·AffordabilityHeadroom(i)      ← don't discount those who can pay
          , 0 , d_max(tier(i)) )
```

| Tier | Qualification | `d_max` | Preferred instrument |
|---|---|---|---|
| Bronze | < 12 months tenure | 5% | Price discount |
| Silver | 12–36 months, regular recharge | 10% | Discount or bonus MB |
| Gold | 36–84 months, high RFM-LE | 15% | **Off-peak bonus data** |
| Platinum | 84+ months or top value decile | 20% | **Off-peak data + on-net minutes** |

**(b) Off-peak offloading.** Peak-hour capacity is what drives network capex, so shifting load has real avoided-capex value beyond the near-zero marginal cost of a bit at 03:00. Two refinements over a naive "night bundle":

**Per-cell trough detection.** Rather than asserting a fixed off-peak window, each cell's own 24-hour load curve is analysed to find its minimum-utilisation band, and the offer's validity hours are set **per site**. A congested Tripoli sector and a lightly loaded Ghat sector get different windows. This is more accurate than a blanket claim and it demonstrates that the offer is driven by measured load rather than assumption.

**Cannibalisation guard.** A cheap large night bundle will pull heavy users down from the monthly combo, losing ARPU on subscribers who were never going to leave. Eligibility therefore excludes subscribers whose peak-hour usage would simply shift rather than grow, the night pack is structured as **additive rather than substitutable**, and a simulated margin check runs before any cohort is approved. This is the single most important commercial critique of the idea and the proposal answers it explicitly.

**Guardrails (enforced in code, tested in CI):**

1. **Margin floor** — `P(i,b) ≥ variable_cost(b) × (1 + min_margin)`. No loss-making offer.
2. **CLV ceiling** — cumulative 12-month discount ≤ 15% of predicted CLV.
3. **Budget constraint** — cohort allocation solved as a knapsack / LP (`PuLP`): maximise expected retained margin subject to total discount cost ≤ budget.
4. **Cannibalisation guard** — subscribers with low churn risk *and* high value are excluded. They would have paid full price.
5. **Fairness** — no pricing on protected or proxy-protected attributes. District enters only as a *network-quality* input, never as a socioeconomic price lever, and a post-hoc audit checks discount distribution across districts for redlining.
6. **Auditability** — every decision persists inputs, weights, active constraints and reason codes to `decision_log`, replayable on demand.

**Value-add before discount.** A 15% headline cut permanently reduces realised ARPU and is trivially matched by a competitor. A gigabyte of off-peak data costs almost nothing on an idle sector, is perceived as generous, and leaves the published price sheet intact. The engine converts discount budget into off-peak capacity wherever `offpeak_data_ratio` shows the subscriber will actually use it.

#### M4 — Smart Advance: replacing a static gate with a learned limit

**Chapter 5.** This module is not a new product. Libyana already runs airtime lending; what it lacks is differentiation. We replace one binary rule with a learned exposure limit.

**The current rule:** 12 months tenure, yes or no. Same facility for a nine-year high-ARPU subscriber and a thirteen-month sporadic one.

**Our design:** classic credit-risk framing applied to airtime.

```
Limit(i) = min(
    f( PD(i) )              ← repayment probability, learned
  , g( LoyaltyTier(i) )     ← tier ceiling
  , h( CLV(i) )             ← never advance beyond recoverable value
  , cap_regulatory )
```

`PD(i)` is a **second prediction head sharing M1's feature pipeline** — not a separate model with its own infrastructure. Target: `advance_repaid_within_7d`, matching the operator's real grace period. This is why M4 is cheap to build despite being the most differentiated idea in the project.

**Safety guards, all mandatory:**

| Guard | Rationale |
|---|---|
| **Chronic-distress exclusion** | Subscribers whose recharge pattern shows sustained rather than temporary shortfall are excluded, regardless of PD. Repeated advancing to the most financially stressed subscribers is how digital credit has gone wrong elsewhere. |
| **Cooling-off period** | Minimum interval between advances, and a monthly cap on count and cumulative exposure. |
| **CLV-bounded exposure** | Never advance more than a fraction of recoverable lifetime value. |
| **Line-reset risk score** | A separate flag when the recommended limit carries meaningful probability of pushing the line to recharge stage. The system's job is to prevent that outcome, not to optimise recovery after it. |
| **Fee structure flagged for review** | Any service fee is modelled as a **fixed charge, never time- or percentage-based**. Libya's financial framework makes interest a live question, and we flag the structure for Shariah review rather than claiming to have resolved it. |
| **Reject inference** | Repayment is only observed for subscribers who were granted an advance, which is textbook selection bias. The report documents the bias and applies a reject-inference correction. |

**The headline insight for the pitch:** the operator's retention product is currently a churn mechanism. An advance the subscriber cannot clear in seven days sends the line to incoming-only, and eventually the number is reset and resold. **A static limit guarantees this happens to some subscribers every month.** A learned limit is not a nice-to-have; it is a fix for operator-caused hard churn.

#### M5 — Network-Experience Fusion via AutoEncoder

**Chapter 9.** Anomaly detection by reconstruction error, which is the canonical AutoEncoder application.

1. Each cell's **24 × 30 hourly load matrix** is flattened and fed to an AutoEncoder trained only on normal-operation cells.
2. Encoder compresses to a small latent vector; decoder reconstructs. **Reconstruction error is the degradation score** — cells with outages, congestion collapse or fuel-driven downtime reconstruct poorly because the network never learned that pattern.
3. STL decomposition provides a classical baseline for comparison, so the choice of AutoEncoder is evidenced rather than assumed.
4. Each subscriber receives an **exposure-weighted degradation score** across their home cell and top-3 visited cells.
5. That score enters M1 as a feature. Its **SHAP contribution share** then yields *network-attributable churn risk*.
6. Aggregating contribution × CLV up to the site produces the headline artefact: **revenue-at-risk in LYD, per tower, on a map of Libya.**

**Role:** this converts a marketing model into a **capex prioritisation tool**. The NOC receives a ranked list of sites where a generator upgrade or backhaul fix carries a quantified revenue return.

The AutoEncoder's latent vector is also reused as a compact cell embedding in the off-peak trough detection of M3, which is a small but real piece of architectural economy.

#### M6 — Arabic Care-Text Intelligence

**Chapters 7 and 10.** Promoted from stretch goal to core module, because it is the one place in this project where deep learning is unambiguously the right tool, and because no competing team will have an Arabic NLP component.

**Pipeline, following Chapter 7's unit structure:**

1. **Text mining and preprocessing** (Units 1–2): Arabic normalisation (alef and hamza forms, taa marbuta), diacritic stripping, tokenisation, dialect handling for Libyan Arabic, and RTL-safe rendering with `arabic-reshaper` and `python-bidi`.
2. **Language model** (Unit 3): a pre-trained Arabic transformer — CAMeL-BERT, MARBERT or AraBERT — selected by validation performance on the dialect set.
3. **Fine-tuning with LoRA** (Ch 10 Unit 2): parameter-efficient adaptation, training a small number of adapter parameters rather than the full model. This is what makes the module feasible on a free T4 in roughly twenty minutes.
4. **Baseline comparison** (Ch 7 Unit 4): a simple Keras embedding-plus-dense classifier, so the value of the pre-trained transformer is measured rather than assumed.

**Output:** each care ticket maps to a reason code (coverage, pricing, billing, speed, service, device) plus sentiment. The reason code becomes a feature in M1, closing a loop most churn projects never attempt: **complaint text becomes a churn predictor and a targeting input.** Reason distributions per district also feed the network map.

#### M7 — CVM Copilot

**Chapter 10, Unit 4.** A LangChain agent that lets a non-technical marketing analyst interrogate the entire system in plain language.

**Example:** *"Which Benghazi subscribers are at risk because of coverage, and what should we offer them?"*

The agent decomposes this into tool calls:

| Tool | Function |
|---|---|
| **DuckDB SQL tool** | Query the feature store for the district cohort |
| **Model API tool** | Call `/v1/score/churn`, `/v1/network/site-risk`, `/v1/offer/next-best` |
| **RAG retriever** | Vector search over model cards, the data dictionary and the guardrail documentation, so the agent can explain *why* an offer was chosen |

It returns a grounded natural-language answer with the cohort attached and an export button.

**Design constraints, stated explicitly:**

- The LLM **never sets prices or limits**. It reads from the decision engine and explains. All pricing and credit decisions come from M3 and M4 under their guardrails. An LLM is not permitted anywhere in a path that moves money.
- Every answer cites the tool output it came from. No ungrounded claims.
- Served through a hosted inference API (Groq, OpenRouter or HuggingFace Inference), not self-hosted, to keep the runtime footprint at zero GPU.

**Why this is the strongest demo asset.** It is Week 6 material applied to something that is not a generic chatbot, it makes six other modules legible to a non-technical audience in a single interaction, and it directly serves the Chapter 1 objective about commercialising AI service applications.

### 3.3 The Retention Ladder: three stages of intent to leave

Not a separate module. A **delivery policy layer** over M1b and M3, which is why it costs almost nothing to build.

Intervention intensity scales with how long the line has been cold, but with two refinements that most operators get wrong.

**Stage boundaries come from the hazard function, not from intuition.** Rather than picking 7 / 30 / 60 days by feel, the Kaplan-Meier and hazard curves from M1b identify where recovery probability falls sharply. Those inflection points become the stage cut-points, and they are recomputed per segment.

| Stage | Trigger | Intervention | Instrument |
|---|---|---|---|
| **1 — Cooling** | Recharge gap exceeds the subscriber's own baseline | Low-cost nudge | Reminder SMS, small off-peak bonus, advance-limit reminder |
| **2 — Cold** | Past the first hazard inflection | Peak spend | Personalised priced bundle, loyalty bonus, on-net pack if leakage detected |
| **3 — Dormant** | Past the second inflection | **Reduced spend** | Single low-cost win-back, then stop |

**The inverted-U.** Most operators escalate the discount as the line gets colder, which is backwards. Recovery probability collapses faster than the offer value rises, so expected return per LYD spent peaks in the middle and falls away. Optimal spend is low, then high, then **low again**. Stating this in the pitch signals an understanding of retention economics rather than retention mechanics.

**Sleeping-dogs guard.** Contacting a dormant-but-not-departing subscriber can remind them to leave. The uplift model's negative-effect quadrant is excluded from all three stages.

**Uplift method.** A simple two-model difference (treated response model minus control response model), not a causal-inference library. At this data scale the extra machinery of EconML buys precision we cannot validate on synthetic response anyway, and the simpler method is defensible in a three-minute pitch.

---

## 4. User Interfaces & Deliverables

### 4.1 CVM Command Center (operator-facing)

Streamlit, six screens.

| Screen | Contents |
|---|---|
| **Executive Overview** | Subscribers at risk (30d), **revenue at risk in LYD**, base composition by tier, churn trend, retained-revenue simulation against a do-nothing baseline |
| **Segment Explorer** | RFM-LE heatmap, dendrogram from hierarchical clustering, PCA scatter of K-Means clusters, per-segment behaviour cards |
| **Subscriber 360** | Lookup by hashed ID → churn probability from both arms, survival curve, RFM-LE scores, CLV, **SHAP waterfall in plain language**, recommended offer with computed price, **advance limit with its reason**, retention stage |
| **Campaign Builder** | Filter cohort → set LYD budget → uplift simulation → expected retained subscribers, cost, net margin → export targeting CSV |
| **Network Risk Map** | Libya map on **real OpenCelliD MCC-606 coordinates**, sites coloured by AutoEncoder reconstruction error and network-attributable revenue-at-risk, drill-down to affected subscribers and their complaint reason mix |
| **Voice of Customer** | M6 output: reason-code distribution by district and segment, sentiment trend, sample tickets rendered in Arabic RTL |

### 4.2 Subscriber Channel Simulator

A mock of the channels a Libyan prepaid customer actually uses: a **USSD menu flow** including a `*61121#`-style advance option, and an **SMS preview**, in **Arabic RTL with an English toggle**. Entering a test subscriber shows the exact offer, price and advance limit the engine selected, with the message copy generated by the LLM and grounded in the engine's reason codes.

Low engineering cost, disproportionate demo impact. It collapses the distance between "we built a model" and "here is what the customer receives."

### 4.3 CVM Copilot

Chat surface over the LangChain agent described in §3.2, with visible tool-call traces so evaluators can see it is grounded rather than hallucinating.

### 4.4 Prediction & Decision API

FastAPI with auto-generated OpenAPI docs, Pydantic v2 contracts, structured errors, `/health`. Single and batch modes. Target **p95 < 200 ms** on one CPU container for tabular endpoints, verified with `locust` against the Cell2Cell holdout. Text and copilot endpoints have separate, looser latency budgets, stated honestly.

### 4.5 Deliverables Checklist

| # | Deliverable | Acceptance criterion |
|---|---|---|
| D1 | GitHub repository | `docker compose up` reproduces the system from a clean clone |
| D2 | GAN synthesis engine | Passes the SDMetrics gate; seeded and reproducible; CTGAN vs TVAE vs Copula comparison reported |
| D3 | M1 benchmark report | LightGBM vs LSTM with calibration curves, PR-AUC, lift, and a written architecture verdict |
| D4 | All trained models + MLflow runs | Params, metrics and artefacts logged for every experiment |
| D5 | FastAPI service | Live Swagger docs, p95 latency evidence |
| D6 | Command Center | Six screens functional on generated data |
| D7 | Channel simulator | Arabic RTL rendering verified |
| D8 | CVM Copilot | Grounded answers with visible tool traces |
| D9 | Technical report (~20 pp) | Methodology, results, honest limitations |
| D10 | Model cards | One per model: intended use, data, metrics, limitations, ethics |
| D11 | Data dictionary | Every field: type, source (real vs generated), generation logic |
| D12 | Syllabus coverage matrix | Appendix B, evidenced with file paths |
| D13 | 3-minute pitch deck + 5-minute demo video | Video doubles as live-demo insurance |

---

## 5. Complete Tech Stack

Every component is free, open-source or free-tier. Serving is CPU-only. Two modules train on free-tier GPU.

### 5.1 Data Engineering

| Tool | Purpose |
|---|---|
| Python 3.11 | Runtime |
| pandas / **Polars** | Transformation; Polars for Cell2Cell-scale joins |
| **DuckDB** | Embedded analytical SQL — the feature store and the Copilot's SQL target. No database server to operate |
| PyArrow / Parquet | Columnar storage, partitioned by snapshot date |
| NumPy | Sequence tensor construction for the LSTM |
| **Pandera** | Schema contracts and data-quality assertions in CI |
| **SDV** (CTGAN, TVAE, GaussianCopula) | Adversarial and classical synthesis |
| **SDMetrics** | Synthetic fidelity gate |
| Faker | Locale-aware categorical fields |

### 5.2 Classical Machine Learning (Ch 5, 6)

| Tool | Purpose |
|---|---|
| scikit-learn | Pipelines, preprocessing, calibration, Decision Tree, Naïve Bayes, KNN, SVM, K-Means, hierarchical clustering, PCA, metrics |
| **LightGBM** / XGBoost / CatBoost | Gradient-boosted ensembles |
| imbalanced-learn | SMOTE / ADASYN comparison arm |
| **lifelines** / scikit-survival | Cox PH, Random Survival Forest, Kaplan-Meier |
| **lifetimes** | BG/NBD + Gamma-Gamma CLV |
| **SHAP** | Global and local explainability |
| **Optuna** | Hyperparameter search, 50 trials max per model |
| **PuLP** / scipy.optimize | Budget-constrained discount allocation |
| scipy | Per-cell trough detection, statistical tests |

### 5.3 Deep Learning (Ch 8, 9)

| Tool | Purpose |
|---|---|
| **TensorFlow / Keras** | LSTM churn arm, AutoEncoder anomaly detection, Keras NLP baseline |
| Keras callbacks | EarlyStopping, ReduceLROnPlateau, ModelCheckpoint |
| TensorBoard | Training curves, overfitting diagnosis |
| scikit-learn | Sequence scaling and temporal fold construction |

### 5.4 NLP & LLM (Ch 7, 10)

| Tool | Purpose |
|---|---|
| **HuggingFace `transformers`** | Pre-trained Arabic encoders; `pipeline()` API (Ch 10 Unit 1) |
| **CAMeL-BERT / MARBERT / AraBERT** | Arabic language models |
| **`peft`** | LoRA / QLoRA parameter-efficient fine-tuning (Ch 10 Unit 2) |
| `datasets`, `evaluate` | Training data handling and metrics |
| `bitsandbytes` | Quantisation for lightweight deployment (Ch 10 Unit 3) |
| **LangChain** | Copilot agent, tool routing, prompt orchestration (Ch 10 Unit 4) |
| **ChromaDB** or FAISS | Vector store for RAG over model cards and documentation |
| Groq / OpenRouter / HF Inference | Hosted LLM inference, free or near-free tier |
| arabic-reshaper + python-bidi | Arabic RTL rendering |
| CAMeL Tools | Arabic normalisation and tokenisation |

### 5.5 MLOps & Quality

| Tool | Purpose |
|---|---|
| **MLflow** | Experiment tracking and model registry across all seven modules |
| **Evidently AI** | Data and prediction drift reports |
| pytest + pytest-cov | Unit and integration tests, including guardrail and leakage tests |
| ruff + black + pre-commit | Lint and format gates |
| **GitHub Actions** | CI: lint → tests → schema checks → leakage check → build |

### 5.6 Serving & Frontend

| Tool | Purpose |
|---|---|
| **FastAPI** + Uvicorn | Inference and decision API |
| Pydantic v2 | Request/response validation |
| joblib / SavedModel / ONNX | Model loading |
| APScheduler | Nightly batch scoring |
| DuckDB *(or PostgreSQL)* | Decision log and campaign store |
| locust | Latency and throughput testing |
| **Streamlit** | Command Center, channel simulator, Copilot chat surface |
| Plotly / Altair | Interactive charts |
| **Folium / pydeck** | Libya tower map |

### 5.7 Deployment & Compute Budget

| Resource | Cost | Purpose |
|---|---|---|
| **Docker + Docker Compose** | Free | One-command reproducible stack |
| **Oracle Cloud Always Free** (4 ARM cores, 24 GB RAM) | **$0** | Always-on demo host. Comfortably runs the full CPU stack |
| **Hugging Face Spaces** free tier | **$0** | Public Streamlit demo, backup host |
| **Google Colab free T4** | **$0** | LSTM training (M1 Arm B), AutoEncoder (M5), LoRA fine-tune (M6) |
| Colab Pro *(optional)* | ~$10 | Only if E6 needs sustained fine-tuning iterations |
| LLM inference credits | ~$10–20 | Groq / OpenRouter / HF Inference for the Copilot |
| Domain name *(optional)* | ~$10/yr | Polish |
| **Total** | **$20–40** | |

**Explicitly not purchased:** rented GPU servers, managed Kubernetes, managed databases, any per-hour GPU instance. Every deep-learning component in this project fits comfortably in a free Colab session. Check the **GitHub Student Developer Pack** (DigitalOcean and Azure credits) and ask SIC coordinators directly whether the programme provides compute before spending anything.

"We built, trained and deployed all of this for under $40" is itself a pitch line.

---

## 6. Execution Plan — 3 Weeks, 6 Engineers

### 6.1 Role Allocation

Each student owns specific modules **and specific syllabus chapters**, so curriculum coverage has a named owner rather than being everyone's vague responsibility.

| ID | Role | Modules owned | **Chapters owned** |
|---|---|---|---|
| **E1** | Data Engineer | Layers 1–3: ingestion, **CTGAN synthesis**, DuckDB feature store, sequence tensors, data dictionary | **9** (GAN) |
| **E2** | ML Engineer — Risk | **M1 both arms** (LightGBM vs LSTM), survival, **M4** repayment PD head | **5, 8, 9** |
| **E3** | ML Engineer — Value | **M2** clustering / PCA / CLV, **M5** AutoEncoder anomaly detection | **5, 6, 9** |
| **E4** | Backend & Pricing | **M3** pricing and off-peak engine, guardrails, FastAPI, Docker, CI | **5** |
| **E5** | Frontend & Copilot | Command Center, channel simulator, **M7 LangChain/RAG agent** | **10** |
| **E6** | NLP, QA & Product | **M6** Arabic LoRA classifier, evaluation harness, model cards, business case, pitch | **7, 10** |

Working agreement: daily 15-minute stand-up, GitHub Projects board, trunk-based development with PR review, hard integration checkpoint at the end of each week.

**Chapter 1** (AI concepts, trends, markets, commercialisation) is covered collectively through the business case, the market analysis in §1, and the technical report's positioning section. E6 owns the write-up.

### 6.2 Sprint Schedule

**Week 1 — Foundations (Days 1–5)**
*Goal: real data flowing, a classical baseline, the Libyan schema locked, GPU environments proven.*

| Day | Milestone |
|---|---|
| 1 | Repo scaffold, Docker skeleton, CI green. All datasets downloaded and licences recorded. **Colab notebooks provisioned and GPU access confirmed for E2, E3, E6** |
| 2 | EDA on all three tabular datasets. UCI deduplication (~300 rows) done and documented. Leakage audit of `Customer Value`. Arabic corpora surveyed |
| 3 | **Libyan schema v1 frozen** — every generated field named, typed and justified. CTGAN training begins |
| 4 | Synthesis engine v1 produces 100k subscribers. SDMetrics gate run. CTGAN vs TVAE vs Copula comparison logged. RFM-LE scoring implemented |
| 5 | ⚑ **Checkpoint 1:** baseline LightGBM on IBM Telco with honest temporal-split metrics. DuckDB feature store live. **Sequence tensors built.** API skeleton returns a stub score |

**Week 2 — Models (Days 6–10)**
*Goal: every model trained, including all deep-learning components, and reachable over HTTP.*

| Day | Milestone |
|---|---|
| 6 | M1 Arm A tuned and calibrated with SHAP working. **M1 Arm B: LSTM architecture built and first training run on Colab.** M2 K-Means and hierarchical clustering complete |
| 7 | **LSTM tuned; benchmark table produced.** Cox survival model. CLV benchmarked against IBM CLTV. PCA visualisation |
| 8 | **M3 pricing engine v1** with all six guardrails and unit tests. Per-cell trough detection. **M4 repayment PD head trained** |
| 9 | **M5 AutoEncoder trained** on cell load matrices; STL baseline compared; OpenCelliD join; revenue-at-risk per site computed. **M6 LoRA fine-tune running** |
| 10 | ⚑ **Checkpoint 2 — feature freeze.** All endpoints live. Command Center screens 1–3 rendering real output. **M6 classifier evaluated against the Keras baseline.** Anything not working by end of Day 10 is descoped, not rescued |

**Week 3 — Integration, Copilot & Pitch (Days 11–15)**
*Goal: a system that survives a live demo and a story that survives an evaluator's questions.*

| Day | Milestone |
|---|---|
| 11 | **M7 Copilot: LangChain agent wired to SQL, model API and RAG retriever.** Retention ladder stage boundaries derived from hazard curves. Campaign Builder screen |
| 12 | Network Risk Map. Voice-of-Customer screen. Channel simulator with Arabic RTL and LLM-generated copy. End-to-end integration test |
| 13 | Hardening: latency test (p95 < 200 ms tabular), Evidently drift report, guardrail test suite, error handling. Business case finalised. **Copilot grounding verified — no ungrounded answers** |
| 14 | Documentation sprint: technical report, model cards, syllabus coverage matrix, README. **Demo video recorded** |
| 15 | ⚑ **Checkpoint 3:** pitch deck finished, three timed dry-runs, deployment verified from a clean machine on Oracle Free Tier |

### 6.3 Descoping Ladder

Agreed in advance so that cutting scope is a decision rather than a panic. Cut strictly in this order:

1. Quantisation experiments in M6 (Ch 10 Unit 3 is still covered by the LoRA work)
2. Copilot RAG layer → agent keeps SQL and model-API tools only
3. Voice-of-Customer dashboard screen → M6 output exposed via API only
4. Hierarchical clustering → K-Means and PCA alone cover Chapter 6
5. Per-cell trough detection → single global off-peak window
6. Optuna tuning → sensible fixed hyperparameters

**Never cut:** the M1 LightGBM-vs-LSTM benchmark, M1 calibration, the M3 guardrails, the M4 credit safety guards, the holdout control group, the data dictionary, or the honest-metrics disclosure. The benchmark and the guardrails are the project's technical and ethical core respectively.

### 6.4 Risk Register

| Risk | L | I | Mitigation |
|---|---|---|---|
| LSTM underperforms and the team treats it as failure | H | M | Reframed in advance: the benchmark is the deliverable, not the winner. Both outcomes are written up as results |
| Colab session limits disrupt training | M | M | Checkpoint to Drive every epoch; all three GPU modules are small enough to finish inside one session; Oracle CPU fallback for the AutoEncoder |
| LoRA fine-tune fails on dialect data | M | M | Keras baseline classifier is built first and always works; transformer is an upgrade, not a dependency |
| Copilot hallucinates and embarrasses the demo | M | H | Agent is read-only, every answer cites its tool output, traces visible in the UI, and scripted demo questions are rehearsed |
| Generated data too clean, models look unrealistically good | H | H | SDMetrics detection gate; deliberate noise and missingness injection; naive and honest metrics both reported with the gap explained |
| Inflated metrics from duplicates or leaky features | H | H | Automated CI leakage test; mandatory temporal splits; `Customer Value` excluded |
| Integration failure in the final week | M | H | Hard Day-10 feature freeze; API contracts agreed Day 3; stub endpoints from Day 5 |
| Live demo failure at pitch time | M | H | Pre-recorded 5-minute video; local Docker fallback; no dependency on venue Wi-Fi |
| Scope creep | H | M | Descoping ladder agreed Day 1; Day-10 freeze non-negotiable |

### 6.5 Ethics, Privacy & Compliance

Prepaid CVM touches pricing, credit, geography and behaviour, which is the exact combination where algorithmic systems cause harm. Explicit commitments:

- **No real subscriber data.** Every record is public-research or generated. Identifiers are SHA-256 with salt; no raw MSISDN exists in the repository at any point.
- **Data residency.** The architecture assumes real CDRs never leave operator infrastructure. The deployable artefact is the container, not a data export.
- **Credit is capped, not maximised.** M4 optimises for subscriber safety and line survival, not for recovery yield. Chronic-distress exclusion and cooling-off periods are mandatory, not configurable.
- **Fee structure flagged, not assumed resolved.** Any service fee is modelled as a fixed charge and referred for Shariah review. We do not claim to have settled the question.
- **No geographic price discrimination.** District influences network-quality features only. A post-hoc audit compares discount distribution across districts to detect redlining.
- **No protected-attribute pricing.** Age group informs offer *relevance*, never price.
- **The LLM never moves money.** M7 reads and explains; it has no write path to pricing or credit decisions.
- **Full auditability.** Every pricing and advance decision logs inputs, weights, active constraints and reason codes, and is replayable.
- **Transparency to the customer.** Every offer carries a human-readable reason ("loyalty reward — 6 years with us"), not an opaque personalised price.
- **Honest claims.** The report states that generated-data metrics are not evidence of production performance, and specifies the real-data validation path required before any deployment decision.

---

## 7. Indicative Business Case

All figures are **illustrative**, built on stated assumptions, and shipped as a spreadsheet so evaluators can change any input. The method is the point, not the number.

**Assumptions (pilot slice):** 1,000,000 addressable prepaid subscribers · 12 LYD monthly ARPU · 3.5% monthly silent churn (~35,000) · model captures ~62% of churners in the top 3 deciles · 120,000 treated per monthly campaign · 10% untreated control.

### 7.1 Retention campaign

| Line | Value |
|---|---|
| Monthly revenue at risk | 35,000 × 12 LYD = **420,000 LYD** |
| Treated cohort | 120,000 |
| Assumed uplift (treatment − control) | 2.5 pp → **3,000 additional retained** |
| Retained value, 12-month horizon | 3,000 × 12 × 12 = **432,000 LYD** |
| Campaign cost @ 1.2 LYD average incentive | **144,000 LYD** |
| **Net contribution** | **288,000 LYD · ROI ≈ 3.0×** |

**Sensitivity — ROI (benefit ÷ cost):**

| | Cost 0.8 LYD | Cost 1.2 LYD | Cost 2.0 LYD |
|---|---|---|---|
| **Uplift 1.0 pp** | 1.8× | 1.2× | 0.7× ⚠ |
| **Uplift 2.5 pp** | 4.5× | 3.0× | 1.8× |
| **Uplift 4.0 pp** | 7.2× | 4.8× | 2.9× |

The loss-making cell is left visible on purpose. It defines the operating envelope and shows the model managing risk rather than flattering the proposal.

### 7.2 Avoided cannibalisation — the larger prize

A blanket campaign across the full base at the same 1.2 LYD incentive costs **1,200,000 LYD per month** for comparable or worse uplift, because most of the spend lands on subscribers who would have recharged regardless. Targeted selection saves roughly **1,050,000 LYD per month in wasted discount**.

In prepaid CVM, *not* spending is usually worth more than spending better.

### 7.3 Prevented line resets — operator-caused churn

The mechanism from §1.2 P6, quantified.

| Line | Value |
|---|---|
| Advance-eligible base (past the 12-month gate) | ~600,000 |
| Monthly advance users | ~150,000 |
| Non-settlement within the 7-day grace period @ 4% | 6,000 → recharge stage |
| Terminal line reset @ 15% of those | **900 lines reset and resold per month** |
| Value of each reset (remaining CLV ≈ 12 LYD × 24 months) | 288 LYD |
| **Monthly loss from mis-set advance limits** | **~259,000 LYD** |
| Assumed reduction from learned limits (40%) | **~104,000 LYD per month recovered** |

This is churn the operator is currently causing to itself. It is also the cheapest to fix, because the facility, the billing integration and the recovery mechanics already exist. Only the limit-setting logic changes.

### 7.4 Capex prioritisation

M5 outputs revenue-at-risk in LYD per cell site, converting network investment from a coverage-map argument into a ranked, financially quantified list. Not modelled here, but the artefact is a deliverable.

---

## 8. SIC Evaluation & Pitch Highlights

### 8.1 The Four Points to Land

**① Localisation is a technical contribution, not a coat of paint.**
Most capstone churn projects train on a US postpaid dataset with a "Contract Type" column and call it telecom AI. Libya is overwhelmingly prepaid: no contract, no cancellation, no churn event. We **redefined the target variable** (30 days of zero revenue-generating events), **redefined RFM** for a market with no purchase transactions, and engineered a **dual-SIM leakage detector** from the incoming-to-outgoing call ratio. The geography is real Libyan tower data from OpenCelliD. The complaint classifier reads Libyan Arabic. This problem cannot be solved by downloading a Kaggle notebook.

**② We found a churn mechanism the operator built itself.**
Libyana's published FAQ describes an airtime Credit Loan with one eligibility rule: twelve months of tenure. Seven days to settle. Fail, and the line degrades to incoming-only. Never settle, and the number is reset and resold. **A static limit guarantees that outcome for some subscribers every month — the retention product is manufacturing hard churn.** We replace the binary gate with a learned limit bounded by repayment probability, loyalty and lifetime value, with chronic-distress exclusion so the system protects lines rather than maximising recovery. Roughly 104,000 LYD a month, from logic changes alone.

**③ Full-stack AI, with a defended architecture choice.**
Classical ensembles and clustering, a CTGAN generating the subscriber population, an LSTM benchmarked head-to-head against gradient boosting, an AutoEncoder detecting cell degradation by reconstruction error, an Arabic transformer fine-tuned with LoRA, and a LangChain agent making all of it queryable in plain language. Critically, **we do not claim the neural network wins.** We ran the benchmark, report whichever arm performed better, and explain why. On short, sparse prepaid sequences gradient boosting is very hard to beat, and knowing that is worth more than defaulting to a deep model because it sounds advanced.

**④ Intellectual honesty as a differentiator.**
Published work on our primary dataset reports ~97% accuracy and ~0.99 AUC. We reproduce those numbers and then show they are **wrong**: inflated by ~300 duplicate rows and by a pre-computed `Customer Value` field that leaks the outcome. We deduplicate, drop the leaky feature, split temporally, and report the lower honest figures alongside the naive ones. We state that generated-data metrics are not evidence of production performance. **We would rather show a defensible 0.78 PR-AUC than an indefensible 0.99.**

### 8.2 Three-Minute Pitch Structure

| Time | Beat | Content |
|---|---|---|
| **0:00–0:20** | Hook | "In Libya, customers don't churn. They just stop topping up. About 420,000 LYD a month walks out silently." |
| **0:20–0:45** | The twist | "And their own retention product makes it worse. One rule — twelve months tenure — decides who can borrow airtime. Get the limit wrong, the line goes incoming-only, then the number is reset and resold. The operator is causing hard churn." |
| **0:45–1:35** | **Live demo** | Subscriber 360: one ID → risk, survival curve, SHAP explanation, personalised offer, advance limit with its reason. Then the **Copilot**: type "which Benghazi subscribers are at risk from coverage, and what should we offer?" and watch it query, score and answer |
| **1:35–2:20** | Technical depth | CTGAN population. LightGBM vs LSTM benchmark with the honest verdict. AutoEncoder site degradation on the Libya map. Arabic LoRA classifier. Calibrated probabilities into constrained optimisation with margin, CLV, budget and credit guardrails |
| **2:20–2:45** | Commercial case | ROI ≈ 3.0× with the sensitivity table shown including the loss-making cell. 1.05M LYD/month avoided cannibalisation. 104k LYD/month in prevented line resets |
| **2:45–3:00** | Close | "Every chapter of this course, applied to one product. Six students, three weeks, under forty dollars. One command to run it." |

### 8.3 Anticipated Evaluator Questions

| Question | Prepared answer |
|---|---|
| *"Your data is generated — how do we know it works?"* | We don't, and we say so. Structure is learned adversarially from three real telecom datasets and gated by fidelity tests including a discriminator detection test. The deliverable is a validated pipeline and schema; the real-data validation path is specified in §6.5. |
| *"Why isn't everything deep learning?"* | We benchmarked it. On tabular telecom data gradient boosting matched or beat the LSTM at a fraction of the compute, and SHAP gives regulator-grade explanations. Deep learning is used where it wins: sequence modelling, anomaly detection, Arabic text, and the agent layer. |
| *"Why isn't the LLM making the pricing decisions?"* | Because an LLM has no place in a path that moves money. It reads from the decision engine and explains. Pricing and credit come from constrained optimisation with auditable guardrails. |
| *"How is this different from any churn project?"* | Churn prediction is one of seven modules. The product is the pricing, offer and credit-limit decision, with uplift targeting and margin guardrails. And we found a churn source the operator didn't know it had. |
| *"What breaks first at scale?"* | The feature store. DuckDB is correct at demo scale; at 6M+ subscribers it becomes Spark or a columnar warehouse with the same schema. Models and decision logic are unchanged. |
| *"Is personalised pricing fair?"* | Only upward: discounts and bonuses, never surcharges. No protected attributes, no geographic price discrimination, full decision audit log, human-readable reason on every offer. |
| *"Is the airtime advance ethical?"* | It is the reason we built chronic-distress exclusion, cooling-off periods and CLV-bounded exposure. The objective function is line survival, not recovery yield. The fee structure is flagged for Shariah review rather than assumed settled. |

---

## Appendix A — Dataset Quick Reference

| ID | Dataset | Size | Access | Licence | Role |
|---|---|---|---|---|---|
| A | Iranian Churn (UCI 563) | 3,150 | `fetch_ucirepo(id=563)` | CC BY 4.0 | Primary: prepaid, MENA, call-failure feature |
| B | Cell2Cell (Duke/Teradata) | 71,047 | Kaggle `jpacse/datasets-for-churn-telecom` | Public research | Scale, trend features, LSTM viability |
| C | IBM Telco Churn | 7,043 | IBM sample / Kaggle mirrors | Public sample | Benchmark, CLTV, churn-reason taxonomy |
| D | OpenCelliD | MCC 606 subset | `opencellid.org` API | CC BY-SA | Real Libyan tower geography |
| E | Arabic corpora (ASTD, ArSAS) | varies | public research | varies | M6 pre-training signal |

## Appendix B — SIC Syllabus Coverage Matrix

| Chapter | Units covered | Where it appears | Owner |
|---|---|---|---|
| **Ch 1** Introduction to AI | Concepts, applications, techniques, trends & markets, roadmap | §1 market analysis, §7 business case, technical report positioning section | E6 |
| **Ch 5** Machine Learning 1 (Supervised) | U1 ML-based analysis · U2 numerical prediction · U3 classification · U4 Decision Tree · U8 Ensemble · hyperparameter tuning | M1 Arm A (LightGBM, XGBoost, CatBoost, Decision Tree baseline), M2 CLV regression, M3 elasticity, M4 repayment PD, Optuna tuning | E2, E3, E4 |
| **Ch 5** (cont.) | U5 Naïve Bayes · U6 KNN · U7 SVM | Baseline comparison arms in the M1 benchmark table, reported not discarded | E2 |
| **Ch 6** Machine Learning 2 (Unsupervised) | U1 unsupervised algorithms · U2 hierarchical clustering · U3 non-hierarchical (K-Means) · U4 PCA / linear factor model | M2 segment discovery: dendrogram, K-Means with silhouette/elbow, PCA 2-D visualisation | E3 |
| **Ch 7** NLP & Language Models | U1 text mining · U2 preprocessing · U3 language model · U4 NLP with Keras | M6: Arabic normalisation and tokenisation, pre-trained encoder, Keras baseline classifier | E6 |
| **Ch 8** Neural Networks & Deep Learning | Build and train deep NNs · prevent overfitting and vanishing gradients · TensorFlow and Keras proficiency | M1 Arm B: LSTM in Keras with dropout, early stopping, and a written explanation of why gating solves vanishing gradients on 90-step sequences | E2 |
| **Ch 9** Various Deep Learning Topics | U2 RNN for sequential data · LSTM · AutoEncoders · U3 GAN | M1 Arm B (LSTM), M5 (AutoEncoder anomaly detection by reconstruction error), Layer 2 (**CTGAN generating a non-existent subscriber population**) | E1, E2, E3 |
| **Ch 9** (cont.) | U1 CNN | **Not covered.** Deliberate: no image data in this problem, and a contrived usage-grid-as-image framing would weaken rather than strengthen the work. Stated openly in the report |
| **Ch 10** LLMs | U1 HuggingFace pipeline API · U2 fine-tuning with LoRA/QLoRA · U3 optimisation and lightweight techniques · U4 LangChain, RAG, agents | M6 (LoRA fine-tune, quantisation), M7 (**LangChain agent with SQL, model-API and RAG tools**) | E5, E6 |

**Honest note on Chapter 9 Unit 1.** CNN is the one unit this project does not exercise. The problem domain contains no image data. We considered treating each subscriber's 24×30 usage matrix as an image, but a convolution over that grid has no principled locality structure to exploit, and forcing it would produce a worse model and a weaker story. We state the gap rather than disguising it, which is consistent with the project's overall stance on honest reporting.

## Appendix C — Definition of Done

A module is complete only when it: (1) has unit tests in CI; (2) is reachable through the API; (3) is visible in the UI; (4) is logged in MLflow with metrics; (5) has a model card or data-dictionary entry; (6) has its syllabus chapters mapped in Appendix B with a file path; and (7) survives `docker compose up` from a clean clone on a machine that is not the author's.
