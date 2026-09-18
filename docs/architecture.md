# Architecture

Nine layers, four containers, CPU-only at serving time, under 3 GB RAM.
The LSTM benchmark arm trains separately on a free Colab T4 and ships as a
saved artefact.

This is `ali_branch` — Component 3 of the platform. The Employee Copilot
(Component 5) and Customer Chatbot (Component 4) sit *above* Layer 6 and
consume it over HTTP; they are not in this repository. See
[INTEGRATION.md](INTEGRATION.md).

Full narrative: [the proposal](proposal/AI_CVM_Suite_SIC_Proposal_v2.md).
This document is the map from that narrative to the code.

---

## Layer map

| Layer | What it does | Code | Config | Owner |
|---|---|---|---|---|
| **0** Sources | UCI Iranian · Cell2Cell · IBM Telco | — | `conf/data.yaml` | E1 |
| **1** Ingestion | Pandera contracts, dedup, SHA-256 hashing, raw → Parquet | [`src/cvm/ingest/`](../src/cvm/ingest) | `conf/data.yaml` | E1 |
| **2** GAN synthesis | CTGAN / TVAE / Copula, quantile mapping, overlays, quality gate | [`src/cvm/synthesis/`](../src/cvm/synthesis) | `conf/data.yaml#synthesis` | E1 |
| **3** Feature store | Rolling aggregates, RFM-LE, decay, leakage, sequences, DuckDB | [`src/cvm/features/`](../src/cvm/features) | `conf/features.yaml` | E1 |
| **4** Models | M1 churn, M2 value, M3 uplift, M4 advance + MLflow | [`src/cvm/models/`](../src/cvm/models) | `conf/models/` | E2, E3 |
| **5** Decision engine | Worthwhile? Which action? **Guardrails** | [`src/cvm/decision/`](../src/cvm/decision) | `conf/pricing.yaml`, `conf/advance.yaml` | E4 |
| **6** Serving API | FastAPI, Pydantic v2, p95 < 200 ms tabular. **Also the integration surface.** | [`src/cvm/api/`](../src/cvm/api) | `conf/config.yaml#api` | E4 |
| **7** Surfaces | Command Center · Channel Sim | [`apps/`](../apps) | — | E5 |
| **8** MLOps | Docker Compose, GitHub Actions, pytest, MLflow, Evidently | [`docker/`](../docker), [`.github/`](../.github), [`tests/`](../tests) | — | E4 |

Above Layer 6, outside this repository: the Employee Copilot and the Customer
Chatbot. They call the API read-only. See [INTEGRATION.md](INTEGRATION.md).

---

## Data flow

```
Layer 0   [UCI 3,150]      [Cell2Cell 71,047]      [IBM 7,043]
                 |                   |                    |
                 +-------------------+--------------------+
                                             v
Layer 1   INGESTION            Pandera contracts | dedup (~300 UCI dups)
                               MSISDN -> SHA-256+salt | raw -> Parquet

                                             v
Layer 2   GAN SYNTHESIS        Generator --(rows)--> Discriminator
                               CTGAN (primary) | TVAE | Copula (baseline)
                                        |
                               quantile -> LYD ladder
                               overlays: outage, salary week, weekend, credit
                                        |
                               [ GATE: KS >= 0.85 | corr d <= 0.10 | det AUC <= 0.65 ]
                                        |  reject -> retrain
                                             v
Layer 3   FEATURE STORE        rolling 7/30/90d | RFM-LE quintiles
          (DuckDB + Polars)    decay & leakage ratios | weekly rhythm
                               subscriber-level network quality
                               ----------------------------------------
                               features_offline.parquet   (training, PIT-correct)
                               sequences_offline.npz      (90 x k, for the LSTM)
                               features_online.duckdb     (serving)
                                             v
Layer 4   MODELS
            M1  Arm A LightGBM (engineered)  vs  Arm B LSTM (raw sequences)
                + Cox PH survival -> time-to-churn window
            M2  RFM-LE rules || K-Means || Hierarchical || PCA  + BG/NBD CLV
            M4  repayment PD head (shares M1 features)
                                        |
                               [ MLflow Tracking ] -> artifacts/models/
                                             v
Layer 5   DECISION ENGINE      * the commercial core *
            churn_prob --+
            time-to-churn|    +--------------+   +------------------+
            CLV ---------+--> | Uplift filter|-->| M3 Pricing:      |
            loyalty_idx -+    | persuadables |   | discount / bonus |
            repay_PD ----+    | only         |   | + off-peak offer |
            net_quality -+    +--------------+   +--------+---------+
                                                          |
                                                          v
            GUARDRAILS: margin floor | CLV ceiling | budget LP |
                        cannibalisation | fairness | full decision log
                                                          |
            { offer_id, price_lyd, bonus_mb, valid_hours, advance_limit_lyd,
              stage, reason_codes[], expected_margin_lyd }
                                             v
Layer 6   API (FastAPI)        /v1/cohort/query     /v1/score/churn
                               /v1/offer/next-best  /v1/price/quote
                               /v1/advance/limit    /v1/subscriber/{id}
                               /health
                                     |                       |
                                     v                       v
Layer 7   7a COMMAND CENTER    7b CHANNEL SIM    | OUTSIDE THIS REPO:
          exec KPIs, segments, USSD *61121#,     | Component 5 Employee Copilot
          360, campaigns        SMS, Arabic RTL, | Component 4 Customer Chatbot
                                LLM-written copy | -> read-only HTTP consumers
                                                 | -> see INTEGRATION.md

Layer 8   MLOps                Docker Compose | GitHub Actions | pytest
                               MLflow | Evidently drift | model cards
                               decision audit log | leakage test
```

---

## Runtime footprint

Four containers: `api`, `ui`, `channel-sim`, `mlflow`. CPU-only at serving
time, under 3 GB RAM total. See [`docker-compose.yml`](../docker-compose.yml).

There is no agent container in this branch, which is the strongest possible
enforcement of "the LLM never moves money" — the path does not exist. The
components that do use an LLM reach us over HTTP, read-only.

---

## Temporal framing

Shared by M1 both arms and the M4 PD head, so the comparison is fair and the
credit model cannot see further ahead than the churn model:

```
|<---------- 90d observation ---------->|<-- 15d gap -->|<-- 30d outcome -->|
                                         ^
                                         features must end strictly here
```

Target: zero revenue-generating events for ≥ 30 consecutive days in the
outcome window. Splits are temporal, never random.

---

## Label generation

Because the population is synthetic, the label comes from an **explicit hazard
function** rather than from observation. It is documented here and implemented
in [`src/cvm/synthesis/hazard.py`](../src/cvm/synthesis/hazard.py), for two
reasons: the model needs recoverable signal, and the evaluation has to be
honest about being a simulation ground truth.

`hazard.py` splits its fields into two categories, and confusing them breaks
the project in opposite directions:

- **`LABEL_DRIVER_FIELDS`** are the behavioural fields the hazard is a function
  of: `days_since_last_topup`, `recharge_gap_cv`, and so on. These **stay** in
  the feature matrix. The hazard is built from observable behaviour precisely
  so the signal is recoverable; a model that can see no driver of the label has
  nothing to learn, and every metric would collapse for a reason nobody could
  find.
- **`LABEL_ARTIFACT_FIELDS`** trivially encode the outcome: `hazard_score`,
  `churn_date`, the label itself. These must **never** reach the feature
  matrix. `conf/features.yaml#leakage_controls.excluded_columns` must be a
  superset of this tuple.

`tests/leakage/test_point_in_time.py` asserts both directions — artifacts
excluded, drivers available — and fails the build if either drifts. Without the
first test the project's most likely failure is a model that scores beautifully
by reading its own label back out. Without the second, someone "tightens"
leakage control, guts the feature set, and the collapse looks like a modelling
problem.

**What makes this honest rather than circular** is stated plainly in the
report: these metrics are computed against a simulation whose ground truth we
wrote, so they demonstrate that the pipeline and the decision logic work. They
are not evidence of production performance.

---

## Where things break at scale

An evaluator will ask. The honest answer:

**The feature store breaks first.** DuckDB is correct at demo scale; at 6M+
subscribers it becomes Spark or a columnar warehouse with the same schema.
Models and decision logic are unchanged, because nothing above Layer 3 knows
what the store is made of.

Second: the batch scoring window. APScheduler nightly is fine for 100k
subscribers and inadequate for 6M; that becomes a distributed job, not a cron
line.

Neither is a redesign. Both are the kind of substitution the layering was for.

---

## Decisions worth reading

Recorded in [`adr/`](adr/):

- [0001](adr/0001-record-architecture-decisions.md) — why we keep ADRs at all
- [0002](adr/0002-duckdb-as-feature-store.md) — DuckDB over Postgres or Feast
- [0003](adr/0003-two-model-uplift-over-econml.md) — why not a causal-inference library
- [0004](adr/0004-llm-has-no-write-path.md) — the constraint behind M7's design
