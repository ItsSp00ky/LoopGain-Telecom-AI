# AI Customer Value Management (CVM) — `ali_branch`

**Component 3 of the Telecom AI Platform** · Samsung Innovation Campus, Libya AI 2026

**Operator: Almadar Aljadid — المدار الجديد (MCC/MNC 606-01).**

This branch owns **Customer Intelligence, Retention and Loyalty**: predicting
which prepaid subscribers are silently leaving, what they are worth, and what
offer or credit limit they should get — with a defensible LYD figure attached
to every action.

> In Libya's prepaid market there is no contract, no cancellation and no churn
> event. A customer does not leave. They stop topping up, and the revenue
> disappears without a single row being logged.

[![CI](https://github.com/ORG/REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/ORG/REPO/actions/workflows/ci.yml)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/release/python-3110/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## Where this branch sits

The full platform has five components. This repository is one of them.

| # | Component | Owner | Relationship to this branch |
|---|---|---|---|
| 1 | GIS & Network Planning | teammate | Independent |
| 2 | Network ML — congestion, anomaly detection | teammate | **Supplies** per-subscriber quality signals we consume as churn features |
| **3** | **Customer Intelligence, Retention & Loyalty** | **Ali — this repo** | — |
| 4 | Customer Chatbot | teammate | **Consumes** our offer + eligibility API |
| 5 | Employee Telecom Copilot | teammate | **Consumes** our scoring + cohort API |

Components 4 and 5 talk to this branch over HTTP, read-only. They do not import
this package and they do not query our feature store directly. The full
contract — endpoints, payloads, auth, and a worked example — is in
**[docs/INTEGRATION.md](docs/INTEGRATION.md)**, along with a starter kit for
the Copilot owner in
[docs/integration/copilot_starter/](docs/integration/copilot_starter/).

---

## Quick start

```bash
git clone https://github.com/ORG/REPO.git
cd REPO
git checkout ali_branch
conda env create -f environment.yml
conda activate cvm
copy .env.example .env
```

Then follow **[docs/TESTING.md](docs/TESTING.md)** — a numbered walkthrough
from empty clone to working demo, with a checkpoint after every step.

Running the stack:

```bash
docker compose up
```

| Surface | URL |
|---|---|
| API docs (Swagger) | http://localhost:8000/docs |
| CVM Command Center | http://localhost:8501 |
| Channel Simulator | http://localhost:8502 |
| MLflow | http://localhost:5000 |

Environment details, including the conda path and the Docker demo host:
**[docs/setup.md](docs/setup.md)**.

---

## What it produces

Four outputs per subscriber, all reachable over HTTP:

1. A **calibrated silent-churn probability** plus an estimated time-to-churn window.
2. A **value and loyalty tier** from prepaid-adapted RFM-LE, plus predicted lifetime value.
3. A **dynamically priced offer** — loyalty-weighted, margin-constrained, and
   able to reach for the 1 LYD unlimited morning pass (عروض الصبح, 06:00–11:00),
   which costs the network almost nothing on an idle sector.
4. A **personalised emergency-credit limit** for both of Almadar's advance
   products, replacing rules that gate on the subscriber being broke and
   allocate by "consumption" rather than by repayment probability.

This is deliberately **not a churn prediction project**. A churn score is an input.
The product is the closed loop:

```
predict who is leaking -> quantify what they are worth -> decide what to offer
  -> price it within margin, loyalty and credit guardrails -> deliver it in Arabic
  -> hold out a control group -> measure realised uplift -> retrain
```

---

## Modules in this branch

Four modules. Each answers one question, and each feeds the next.

```
predict churn ──► understand value ──► estimate treatment effect ──► decide
     M1                 M2                      M3               Decision Engine
```

| | Module | Question | Code |
|---|---|---|---|
| **M1** | Silent Churn Engine — gradient-boosting benchmark + Cox | Who is leaving, and *when*? | [`models/m1_churn/`](src/cvm/models/m1_churn) |
| **M2** | Value & Loyalty Tiering — RFM-LE, clustering, PCA, CLV | What are they worth? | [`models/m2_value/`](src/cvm/models/m2_value) |
| **M3** | **Uplift Engine** — two-model, validated on Criteo | Who can actually be **influenced**? | [`models/m3_uplift/`](src/cvm/models/m3_uplift) |
| — | **Decision Engine** | Is intervening **worthwhile**? Which action? | [`decision/`](src/cvm/decision) |
| **M4** | Smart Advance — learned emergency-credit limit | How much credit can we safely extend? | [`models/m4_advance/`](src/cvm/models/m4_advance) |

**"No action" is a first-class outcome.** For most subscribers it is the correct
one — the decision engine only recommends an offer when
`uplift × CLV > offer cost` and every guardrail clears.

**Deliberately out of scope**, because they belong to other components:

- **Network anomaly detection** (Component 2). We consume per-subscriber
  quality signals — dropped-call rate, outage hours — as ordinary churn
  features in M1. We do not model the network, and we model no geography at
  all: no districts, no cells, no coordinates.
- **Care-text classification** (Component 4). Complaint text is the chatbot's
  domain.
- **Employee Copilot** (Component 5). Scaffolding was written and handed to its
  owner: [docs/integration/copilot_starter/](docs/integration/copilot_starter/).

Full specification: **[docs/proposal/](docs/proposal/)**.

---

## Repository layout

```
.
├── conf/                    YAML config. Guardrail thresholds live here, not in code.
├── data/                    Gitignored. `python scripts/download_data.py` refills it.
│   ├── raw/                 Untouched source downloads
│   ├── interim/             Deduplicated, schema-validated, hashed
│   ├── processed/           features_offline.parquet, features_online.duckdb
│   └── synthetic/           CTGAN output — the generated Libyan population
├── docs/
│   ├── TESTING.md           Step-by-step: empty clone -> working demo
│   ├── INTEGRATION.md       The contract for Components 2, 4 and 5
│   ├── setup.md             Local and Docker environment setup
│   ├── architecture.md      Layer-by-layer data flow
│   ├── data_dictionary.md   D11 — every field: type, source, generation logic
│   ├── model_cards/         D10 — one per model
│   └── adr/                 Architecture decision records
├── src/cvm/
│   ├── ingest/              Layer 1 — load, validate (Pandera), dedup, SHA-256 hash
│   ├── synthesis/           Layer 2 — CTGAN / TVAE / Copula + SDMetrics quality gate
│   ├── features/            Layer 3 — RFM-LE, decay, leakage, sequences, DuckDB store
│   ├── models/              Layer 4 — M1 churn, M2 value, M3 uplift, M4 advance
│   ├── decision/            Layer 5 — intervene-or-not, offer selection, GUARDRAILS
│   └── api/                 Layer 6 — FastAPI, incl. the integration surface
├── apps/                    Layer 7 — Streamlit: command center, channel sim
├── tests/
│   ├── guardrails/          Commercial + credit-safety invariants. Never skipped.
│   └── leakage/             Point-in-time correctness. Never skipped either.
├── notebooks/               Exploration only. Anything reusable graduates to src/.
└── HANDOFF.md               Session log — read this first if you are picking up the work.
```

---

## The five design principles

These are what separate this from a classroom churn notebook, and each is
enforced somewhere in `tests/`.

| Principle | In practice |
|---|---|
| **Calibrated, not ranked** | Pricing consumes probabilities as monetary expectations, so a 0.31 must mean 31%. Isotonic calibration; scored on Brier and PR-AUC, **never accuracy**. |
| **Uplift, not propensity** | Budget goes only to *persuadables*. Never to sure things, never to lost causes. |
| **Value-add before discount** | Loyalty is rewarded with the 06:00–11:00 morning pass — near-zero marginal cost on an idle sector — in preference to headline cuts that permanently erode ARPU. |
| **Treat only above break-even** | At a 5 LYD blended incentive against 480 LYD of 12-month value, `uplift × CLV − cost` turns positive only above **1.04 pp** of uplift. Below it the engine recommends no action, whatever the churn score says. |
| **Credit that protects, not traps** | The advance limit is capped by repayment probability, CLV, and what one typical top-up can actually clear. A 5 LYD debt against a 5 LYD smallest card leaves nothing behind when it clears — that is a treadmill, not a service. |
| **Localised by construction** | Target definition, features, geography, offer copy and UI language encode Libyan prepaid reality. |

---

## Non-negotiables

Read these before your first commit. They are enforced in CI.

- **No raw MSISDN, anywhere, ever.** Identifiers are SHA-256 + salt at ingestion.
- **Temporal splits, never random.** Features end strictly before the label
  window opens. `tests/leakage/` enforces this.
- **Any field used to generate a synthetic label is excluded from the feature
  matrix.** So is the UCI `Customer Value` column, which partially encodes the outcome.
- **Accuracy is not a reported metric.** It is meaningless at a 10–30% base rate.
- **No LLM in a path that moves money.** This branch contains no agent at all;
  Components 4 and 5 read from the decision engine and explain it.
- **Every pricing and advance decision is logged** with its inputs, weights,
  active constraints and reason codes, and is replayable.
- **Honest metrics.** Published results on the UCI dataset (~97% accuracy, ~0.99
  AUC) are inflated by ~300 duplicate rows and a leaky feature. We report both
  the naive and the honest figures, and explain the gap.

---

## Common tasks

Windows (no `make` required):

```powershell
pwsh tasks.ps1 setup       # create the conda env and install the package
pwsh tasks.ps1 data        # download every public dataset
pwsh tasks.ps1 lint        # ruff + black --check
pwsh tasks.ps1 test        # pytest, fast subset
pwsh tasks.ps1 guardrails  # commercial + credit-safety invariants only
pwsh tasks.ps1 leakage     # point-in-time correctness only
pwsh tasks.ps1 pipeline    # ingest -> synthesise -> features
pwsh tasks.ps1 api         # uvicorn, hot reload
pwsh tasks.ps1 ui          # Streamlit Command Center
pwsh tasks.ps1 up          # full docker compose stack
```

macOS / Linux teammates: the same targets exist in the [`Makefile`](Makefile).

---

## Data & ethics

Every record is either public research data or generated. No public Libyan CDR
dataset exists, and none should — subscriber data cannot legally or ethically
leave an operator. The corpus is hybrid: real public datasets supply the
statistical structure of telecom behaviour, and a CTGAN adds the Libyan prepaid
layer on top of the operator's real catalogue and tariffs.

**Synthetic metrics are not evidence of production performance.** The
deliverable is a validated pipeline and decision logic with a deployment-ready
schema.

Sources, licences and download links: **[data/README.md](data/README.md)**.

The Libyan layer is anchored to **real operator data**, not invented:

| | |
|---|---|
| [`conf/catalogue.yaml`](conf/catalogue.yaml) | 37 real Almadar bundles across 12 families, plus both emergency-credit products |
| [`conf/market.yaml`](conf/market.yaml) | Confirmed recharge ladder (3/5/10/20/40/100 LYD), calendar, geography |
| [`docs/MARKET_QUESTIONS.md`](docs/MARKET_QUESTIONS.md) | What is confirmed, what is still an estimate, and what would change if an estimate is wrong |

Every value carries a `status:` of `confirmed`, `assumption` or `placeholder`.
Anything still assumed is listed in MARKET_QUESTIONS.md rather than quietly
presented as fact.

---

## License

MIT — see [LICENSE](LICENSE). Third-party datasets keep their own licences
(CC BY 4.0, CC BY-SA, and public-research terms); see [data/README.md](data/README.md).
