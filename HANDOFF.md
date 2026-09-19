# HANDOFF

**Read this first if you are picking up this project** — whether you are a new
AI session, a teammate, or me in three weeks having forgotten everything.

Last updated: **2026-09-19** (session 10)
Branch: **`Ali_Branch`** · Repo root: `D:\Sic` · Owner: **Ali Marghem**
Remote: **[ItsSp00ky/LoopGain-Telecom-AI](https://github.com/ItsSp00ky/LoopGain-Telecom-AI)** (private)

---

## 0. Start here — a fresh Claude Code session in 5 minutes

You have landed in a **finished** component, not a work in progress. Eleven
phases are done, 368 tests pass, and the containerised stack runs. The job is
almost never "build the next thing" — it is "change one thing without breaking
the other ten".

**Read in this order, and stop when you have what you need:**

1. **This file, §2 and §7.** §2 is what exists; §7 is what will bite you.
2. **[`docs/ROADMAP.md`](docs/ROADMAP.md)** — the build order, and more usefully
   a per-phase record of *every bug found and what it taught*. If you are about
   to touch M1, M3 or the decision engine, read that phase's section first.
   Several entries exist specifically so the same mistake is not made twice.
3. **[`docs/TESTING.md`](docs/TESTING.md) Step 7b** — how to drive the running
   system by hand, with subscriber ids chosen to disagree with each other.
4. The module's own docstring. They are long on purpose and explain *why*, not
   what.

**Prove it works before you change anything:**

```bash
python scripts/check_phase.py          # every phase, every invariant
python scripts/progress.py             # 345 of 345 functions implemented
python -m pytest -q                    # 368 passed, 0 xfail
docker compose up -d                   # api :8000, ui :8501, sim :8502, mlflow :5000
```

**You cannot run any of it without a salt.** `cp .env.example .env`, then put a
real 64-hex value in `CVM_HASH_SALT` — the code refuses the placeholder
deliberately. A *different* salt from the one on Ali's machine means every
hash in `data/interim` stops reconciling, so if you are given a copy of the
data you must be given that salt too.

**The data and the models are not in git** and never will be — see §7. A clean
clone gives you code that passes 368 tests and a stack that reports
`/health: degraded` until you run the pipeline (`pwsh tasks.ps1 pipeline`,
~40 minutes) or copy `data/` and `artifacts/` across.

### The five habits this codebase is built on

Match them or the review will be unpleasant:

- **Measure, never assert.** Every number in the docs was produced by running
  something. If you write "this improves X", show the before and after.
- **Mutation-test a test that passes first try.** Break the thing it guards; if
  it still passes, it is not a test. Several entries in the roadmap are tests
  that were found to be vacuous this way.
- **Say the awkward thing.** Logistic regression beats the boosters here
  because the generator is linear. The eight segments are a reporting
  convention, not a discovered structure. Both are written down rather than
  buried, and that is the standard.
- **PENDING is not FAILED.** A missing prerequisite and a broken invariant read
  differently in `check_phase.py`, and conflating them hides real breakage.
- **Comments explain WHY.** What the code does is visible in the code.

### What this component will and will not do

It scores churn, values subscribers, estimates uplift, decides an offer, and
sets an advance limit. **No LLM touches any path that moves money**
([ADR 0004](docs/adr/0004-llm-has-no-write-path.md)) and there is no agent in
this branch at all. If you are on the Chatbot or the Copilot, you consume this
over HTTP, read-only — the contract is
[`docs/INTEGRATION.md`](docs/INTEGRATION.md), and breaking a schema in
`src/cvm/api/schemas.py` is a cross-team event.

---

## 1. What this project is, in four sentences

It is **Component 3 (Customer Intelligence, Retention & Loyalty)** of a
five-component Telecom AI Platform built for Samsung Innovation Campus Libya
2026. It predicts which prepaid subscribers are silently leaving, what they are
worth, what offer they should get, and how much airtime credit can safely be
advanced to them — every decision constrained by margin, lifetime value and
credit-safety guardrails. The market is Libya: overwhelmingly prepaid, so there
is no contract, no cancellation, and no churn event to observe — a customer
does not leave, they just stop topping up. The other four components (GIS,
Network ML, Customer Chatbot, Employee Copilot) belong to teammates and talk to
this one over HTTP.

Full specification: [`docs/proposal/AI_CVM_Suite_SIC_Proposal_v2.md`](docs/proposal/AI_CVM_Suite_SIC_Proposal_v2.md).
Platform-level context: the parent proposal listing all five components.

---

## 2. Current state — one paragraph

**Everything is built, trained, tested and running.** All eleven phases of
[`docs/ROADMAP.md`](docs/ROADMAP.md) are complete: **345 of 345 declared
functions implemented**, **368 tests passing with zero xfail**, **85 phase
checks passing with none failed and none pending**, ruff and black clean. The
full four-service stack builds and comes up, and a real subscriber can be
scored end to end through the containerised API. There are 15 commits on
`Ali_Branch`.

**The pipeline runs start to finish:** ingest and hash → synthesise a 100,000
subscriber Libyan population → build features in DuckDB → M1 churn (calibrated,
plus a Cox time-to-churn) → M2 value (RFM-LE, clustering, BG/NBD CLV) → M3
uplift (two-model, validated on Criteo's real randomised arms) → M4 advance
limits → the decision engine → six HTTP endpoints and six screens.

**The headline results, all measured on generated data** and therefore not
evidence of production performance: M1 PR-AUC 0.4556 with logistic regression
winning the benchmark (the generator is linear — said plainly rather than
hidden); Cox held-out concordance 0.8485; M3 Qini 0.0091 held out after the
in-sample figure of 0.2745 turned out to be training and scoring the same
rows; break-even uplift 1.0417 pp at headline figures and 2.1352 pp at the
median fitted CLV.

**Warm p95 is 54 ms** for a one-subscriber score against a 200 ms budget.
Images are 1.85 GB (api) and 2.08 GB (ui) after dropping the training-only
stack from the serving extra.

**Scope is one pipeline:** predict churn (M1) → understand value (M2) →
estimate treatment effect (M3 uplift) → decide whether to intervene (Decision
Engine), plus M4 emergency credit as one available action. Network anomaly
detection, care-text classification and the Employee Copilot belong to other
components.

**Operator is Almadar Aljadid (المدار الجديد), MCC/MNC 606-01** — not Libyana.
Real catalogue data: 37 bundles across 12 families, the confirmed recharge
ladder, both emergency-credit products. See §3a for what that invalidated.

**No geography anywhere.** No districts, cells, coordinates or OpenCelliD.
`district` is a forbidden field in pricing and a test enforces it. Network
quality survives as a subscriber-level feature because it is real measured
signal, not an invented Libyan field.

**What is left is not code.** A clean-clone build on a machine that is not
Ali's, a contract test against a teammate's component, and three timed
dry-runs of the demo. See §6.

---

## 3. Decisions already taken (do not re-litigate without reason)

| # | Decision | Why |
|---|---|---|
| 1 | **Repo root is `D:\Sic`**, branch `ali_branch` | Working directory when the project started. The GitHub repo name does not have to match the folder. |
| 2 | **Python 3.11, via conda** | scikit-survival and SDV have no wheels for 3.12+. Machine has 3.14 and 3.10 in base — neither works. |
| 3 | **M7 Employee Copilot removed from this branch** | It is Component 5, owned by a teammate. Its scaffolding was written and moved to [`docs/integration/copilot_starter/`](docs/integration/copilot_starter/) as a handover, not deleted. |
| 4 | **LangChain / Chroma / sentence-transformers dropped** | Consequence of #3. Saves ~2.5 GB of install on a machine with ~20 GB free. |
| 5 | **M5 (network AutoEncoder) and M6 (Arabic care text) removed entirely** | Session 3. Network modelling is Component 2; care text is Component 4. Building either here would duplicate a teammate's work. M1 consumes subscriber-level quality signals — dropped-call rate, outage hours — as ordinary churn features instead. Contract in [`docs/INTEGRATION.md`](docs/INTEGRATION.md) §6. |
| 5a | **Geography removed entirely; network quality kept** | Session 3d. No districts, cells, coordinates or OpenCelliD — with M5 gone, geography had no consumer, and `district` survived only to be forbidden by the fairness guardrail. Network quality stays because it is *real measured signal* (UCI `Call Failures`, Cell2Cell `dropvce`), just subscriber-level rather than cell-level. The redlining audit was replaced by a value-decile / tenure-band distribution audit. |
| 5b | **Weekend days kept, deliberately** | Session 3d. Friday–Saturday is a public fact, not an estimate, and it costs one derived boolean. `weekend_usage_share_30d` is one of the few cheap signals of whether a subscriber's mornings are actually free, which is exactly what the morning pass turns on. No usage multiplier — that would be the guessed part. |
| 6 | **All syllabus-chapter tracking removed** | Session 3. `docs/syllabus_coverage.md` deleted; chapter annotations stripped from every docstring, config comment, model card and template. Coverage is no longer a project constraint, so the annotations were noise that would drift. |
| 7 | **Other components integrate over HTTP, never by import** | Four reasons in [`docs/INTEGRATION.md`](docs/INTEGRATION.md) §1: the feature store will be replaced at scale, importers bypass guardrails, importers skip the audit log, independent deploys. |
| 8 | **Guardrail thresholds live in `conf/*.yaml`, never in code** | An evaluator will ask to change one live during the demo. |
| 9 | **Five recommended datasets added beyond the proposal** | Criteo Uplift in particular: it is the only real treatment/control data available, and without it the uplift model in M3 cannot be honestly validated. See `data/README.md`. |

| 10 | **M1 is tabular only — no sequence arm** | Session 3h. 90 timesteps of mostly-zero prepaid activity is a weak sequence signal, the decay ratios already compress the predictive part of it, and it was the only GPU work in the branch. Every model is now CPU-trainable and exactly SHAP-explainable, which the guardrailed decision engine needs. We do **not** claim to have beaten a sequence model — we say we scoped it out. |
| 11 | **Cannibalisation is keyed on the bundle held, not on risk × value** | Session 3h. نت 20 at 35 LYD is the *base* monthly; free mornings do not remove the need for all-day data, so the base is not substitutable and its holders have nowhere to fall. Exposure is confined to subscribers above it, and the loss is the gap between rungs. |

Architecture decisions with fuller reasoning: [`docs/adr/`](docs/adr/).

---

## 3a. ⚠ What the Almadar data invalidated

**Read this before reusing any slide or paragraph from the original proposal.**

The proposal's headline finding was built on **Libyana's** Credit Loan: a
12-month tenure gate, a 7-day grace period, degradation to "recharge stage",
and eventual line reset and resale — *"the operator's retention product is
manufacturing hard churn"*.

**That does not transfer to Almadar.** From their own documentation:

- No tenure gate. Eligibility is **balance ≤ 0.5 LYD** (airtime) or
  **≤ 1 LYD with < 250 MB left** (data).
- No published grace period. Recovery is at the next recharge, with a 48-hour
  auto-settle check.
- **No documented recharge-stage or line-reset mechanism at all.**

Claiming operator-caused hard churn for Almadar would be fabricating the
project's central finding. Do not do it.

**The replacement argument**, which comes straight out of their numbers and is
arguably sharper — full detail in [`conf/advance.yaml`](conf/advance.yaml):

| Finding | Evidence |
|---|---|
| Both products gate on the subscriber being broke — the inverse of a risk filter | balance ≤ 0.5 / ≤ 1 LYD |
| "According to consumption" is not a risk model, and its thresholds are unpublished | operator FAQ wording |
| The data advance has **no tiering whatsoever** | flat 5 LYD for everyone |
| **A 5 LYD debt is exactly the 5 LYD smallest recharge card** — clearing it consumes the whole minimum top-up and returns the subscriber to a zero balance, so the minimum recharge buys nothing and the rational move is to defer it (session 3h; this replaced an earlier "cannot clear it at all" claim and is deliberately weaker) | ladder + product price |
| The two products are mutually exclusive, so distressed subscribers alternate between them — unmonitored | both FAQs |

**Two other changes from the real data:**

- **The off-peak window is the MORNING.** عروض الصبح is 1 LYD for unlimited
  data *and* voice, 06:00–11:00. Not a night bundle. This is good news: M3
  personalises a product that exists, and the operator has already told us when
  its spare capacity is. It also sharpens the cannibalisation guard, because
  06:00–11:00 is real usage time for commuters.
- **ARPU was wrong and is now fixed.** The inherited 12 LYD/month was
  inconsistent with a catalogue whose *base* monthly bundle is 35 LYD. Now
  **40 LYD** (session 3h), giving 480 LYD of 12-month value and a 72 LYD CLV
  ceiling. Revenue at risk is **1.4M LYD/month**. Any figure carried over from
  the old proposal needs recomputing.

---

## 4. What is real vs. what is a stub

**Nothing is a stub.** `python scripts/progress.py` reports **345 of 345
functions implemented, 100%**. There is no `NotImplementedError` left in
`src/`, and `grep -rn "TODO(" src/` comes back empty.

| Layer | Where | What it does |
|---|---|---|
| 1 · Ingest | [`src/cvm/ingest/`](src/cvm/ingest) | Load, Pandera-validate, dedup, SHA-256+salt. 22 protected columns dropped at the Cell2Cell boundary, 12 at IBM Telco |
| 2 · Synthesis | [`src/cvm/synthesis/`](src/cvm/synthesis) | CTGAN/TVAE/Copula + SDMetrics gate, TSTR, a mixture copula for the Libyan layer |
| 3 · Features | [`src/cvm/features/`](src/cvm/features) | RFM-LE, decay, leakage, sequences, DuckDB online store, temporal splits |
| 4 · M1 | [`models/m1_churn/`](src/cvm/models/m1_churn) | Boosting benchmark, isotonic calibration, SHAP, Cox + RSF survival |
| 4 · M2 | [`models/m2_value/`](src/cvm/models/m2_value) | RFM-LE tiering, KMeans/hierarchical, PCA, BG/NBD + Gamma-Gamma CLV |
| 4 · M3 | [`models/m3_uplift/`](src/cvm/models/m3_uplift) | Two-model uplift, Qini with Radcliffe normalisation, four quadrants |
| 4 · M4 | [`models/m4_advance/`](src/cvm/models/m4_advance) | Repayment PD, reject inference, affordability ceiling, lockout risk |
| 5 · Decision | [`src/cvm/decision/`](src/cvm/decision) | Six pricing guardrails, advance limits, the retention ladder, a replayable decision log |
| 6 · API | [`src/cvm/api/`](src/cvm/api) | Six FastAPI endpoints, the integration surface for Components 4 and 5 |
| 7 · Surfaces | [`apps/`](apps) | Four Command Center screens + the USSD/SMS channel simulator |
| 8 · Ship | [`docker/`](docker) | Two Dockerfiles, four services, CI with leakage and guardrails as required jobs |

### Deliberately absent

- No agent, no LLM client in any decision path, no vector store —
  [ADR 0004](docs/adr/0004-llm-has-no-write-path.md).
- No network model and no NLP model. Other components' work.
- No geography of any kind.

### Not in git, by design

`data/`, `artifacts/`, `.env`, every `.parquet`, `.joblib`, `.duckdb` and
`.pkl`. Only `.gitkeep` files and `data/README.md` are tracked. The repository
is **191 files** and holds no subscriber data, no model weights and no secret.

> Note for the team: `customer_churn_prediction/` on `main` commits raw CSV
> datasets and a `.joblib` model. This branch's `.gitignore` forbids both. Not
> a criticism of that work — just be aware the two conventions differ, and
> merging will need a decision about which one wins.

---

## 5. Environment state on this machine

This section describes **Ali's machine**. If you are picking this up elsewhere,
what you need is: Python 3.11, the conda env from `environment.yml`, Docker,
and a `.env` with a real salt. Everything else below is local detail.

| Thing | State |
|---|---|
| **conda `cvm` env** | Python 3.11.16 at `D:\Anaconda\envs\cvm`. Run things with `D:\Anaconda\envs\cvm\python.exe` or `conda activate cvm` first |
| Python (base) | 3.14.6 — **wrong version**, never install into it |
| Git 2.55.0 | `D:\Git` — not on the default PATH |
| GitHub CLI 2.101.0 | `D:\GITHUB_CLI`, authenticated as `ali-margem` |
| Docker 29.8.0 | Running. Both images build; the stack comes up healthy |
| **git remote** | **`ItsSp00ky/LoopGain-Telecom-AI`**, branch `Ali_Branch` |
| **`.env`** | Real 64-char salt, local only, gitignored. Generate a *different* one for CI and the demo host. **Do not regenerate casually** — every hash in `data/interim` stops reconciling |
| **scikit-learn** | **Pinned `>=1.7,<1.8`, and the bound matters.** The artefacts are sklearn pickles and sklearn does not guarantee one minor version loads another's. See §7 |
| **conda env writability** | ⚠ `D:\Anaconda\envs\cvm` is not writable by this user. `pip install` falls back to the user site then fails a cross-drive rename with `WinError 17` *after* the package is in place — it looks broken and worked. `scikit-uplift` and `openpyxl` live in `%APPDATA%\Python\Python311\site-packages` |
| **Free disk** | ~16 GB on C:, ~15 GB on D: — **tight.** Docker's WSL disk reaching 20 GB with 5 GB free on C: crashed the engine mid-build, twice. `docker system df` before a big build |

---

## 6. What to do next

**The code is done.** `python scripts/check_phase.py` passes every phase. What
remains is verification that cannot be done from this machine, plus two
judgement calls that belong to a person.

### Not code — and not optional before the demo

1. **A clean-clone build on a machine that is not Ali's.** Everything is
   verified *here*. That is exactly what the check cannot prove. Clone, create
   the env, add a salt, `pwsh tasks.ps1 pipeline`, `docker compose up`.
2. **The contract test against a teammate's component.** Components 4 and 5
   consume this over HTTP per [`docs/INTEGRATION.md`](docs/INTEGRATION.md).
   Nobody has yet called it from the other side. The starter kit for the
   Copilot owner is in [`docs/integration/copilot_starter/`](docs/integration/copilot_starter/).
3. **Three timed dry-runs of the demo.** Not two. `docs/TESTING.md` Step 7b is
   the script; the subscriber ids there are chosen to disagree with each other,
   which is what makes the point land.
4. **Record the 5-minute demo video** as live-demo insurance.

### Two open decisions that are yours, not the code's

**The tier ceiling dominates the discount formula.** 96.8% of bronze and 80.9%
of platinum subscribers clip at exactly `d_max`, so `d(i,b)` reduces to
`d_max(tier(i))` for most people. `conf/pricing.yaml` specifies
`clip(..., 0, d_max)`; scaling *by* `d_max` instead would change what every
subscriber is charged. That is a pricing-policy decision and it has been left
alone deliberately.

**`conf/market.yaml` still contains assumptions.** Every value carries a
`status:` of `confirmed`, `assumption` or `placeholder`. The assumptions are
listed in [`docs/MARKET_QUESTIONS.md`](docs/MARKET_QUESTIONS.md) rather than
quietly presented as fact, but the report has to either replace them with
operator data or defend them.

### If you are adding something

Follow the phase pattern, which is what produced a codebase with no stubs:
implement → run it → find the bug honestly → write the test (mutation-check it
if it passed first try) → make the phase check real → rewrite the roadmap
section with **measured** results including what broke → full verification →
commit with a message that explains why.

---

## 7. Things that will bite you

Learned the hard way or designed in on purpose:

- **Do not `pip install` into Anaconda base.** It is Python 3.14 and half the
  stack will not resolve. `conda activate cvm` first, every time.
- **Install CPU torch before anything that pulls it** (SDV/CTGAN):
  `pip install torch --index-url https://download.pytorch.org/whl/cpu`.
  Otherwise you download ~1.5 GB of CUDA runtime you will never use.
- **Never use a random train/test split.** There is deliberately no
  `random_split` function in `features/splits.py`, and a test asserts it stays
  absent.
- **Never report accuracy as a headline metric.** Meaningless at a 10–30% base
  rate. Use PR-AUC, lift at deciles 1–3, and Brier.
- **A `GuardrailBreach` is not a test to relax.** It names the constraint and
  the numbers. If a demo needs one loosened, change the demo.
- **`CVM_HASH_SALT` must be a real value.** The code refuses the `.env.example`
  placeholder and refuses to hash without a salt — deliberately. An unsalted
  hash of a 9-digit number space is trivially reversible.
- **Know the difference between a label's drivers and its artefacts.**
  `synthesis/hazard.py` exports both sets and a leakage test cross-checks them
  against `conf/features.yaml`, in *both* directions. `LABEL_DRIVER_FIELDS` are
  behavioural and deliberately **stay** available — a model that can see no
  driver of its label has nothing to learn. `LABEL_ARTIFACT_FIELDS` — the
  hazard score, the churn date, the label itself — must **never** reach the
  feature matrix. Excluding the drivers too would look safe and would gut the
  model; this is the subtlest failure mode in the whole project.
- **The privacy scan can flag its own fixtures.** Negative tests need a string
  that looks like a real MSISDN. Tag such a line `msisdn-fixture` and both the
  pytest check and the CI job will skip it — per line, never per directory.

**Added after five bugs that a green test suite could not see.** Every one
reached a running system and none of them failed a test:

- **A batch of one row is its own worst case, and it is the demo path.** Three
  separate bugs needed exactly that trigger. The median of a single NaN is that
  NaN, so imputing from the batch left it in place and `.astype(int)` turned it
  into `-9223372036854775808` in an API response. A SHAP background taken from
  the rows being explained gives `E[x] = x`, so every contribution is exactly
  zero — with "lowers churn risk" printed under each bar, because `0 > 0` is
  false. **Any statistic a serving path needs must travel on the artefact.**
- **`scikit-learn` is pinned `>=1.7,<1.8` and the upper bound is the point.**
  The artefacts are pickles and sklearn does not guarantee cross-minor
  compatibility. An unbounded `>=` let a rebuild resolve 1.9.1 against 1.7.2
  pickles: everything deserialised, `/health` said `ok`, the container was
  marked healthy, and the first request 500'd. sklearn *did* warn — to stderr,
  inside a container, five times. It now logs at `ERROR`, and
  `registry.smoke_check()` pushes a row through every estimator at startup.
- **Loading is not working.** A readiness check that only proves
  deserialisation will pass for a model that cannot predict. `/health` reports
  a model as unusable when its startup smoke prediction failed, and the
  phase-10 check scores a real subscriber rather than reading a flag.
- **`series.to_frame().T` throws away every dtype.** A Series holds one dtype,
  so the transpose returns every column as `object`. `prepare_matrix` refused
  all 54 and the Subscriber 360 SHAP panel had never rendered once, on any
  subscriber, since the screen was written. It degraded politely and nobody
  read the warning. **Keep the one-row frame; never rebuild one.**
- **A surface that makes decisions must be able to record them.** `ui` and
  `channel-sim` call the decision engine in-process and mounted `./data` as
  `:ro`, so the offer panel died on `[Errno 30] Read-only file system` writing
  the decision log. Invisible locally, because a local run writes to the repo.
- **Check what a baseline is measured against.** The Campaign Builder reported
  "saved 0 LYD against a blanket campaign" beneath a chart saying 227 of 497
  had been removed by guardrails — because "blanket" was computed from the
  post-guardrail pool. The 227 *were* the saving.
- **Know whether a margin is gross or net before you subtract a cost from it.**
  M3's `expected_value_lyd` is already `uplift × CLV − cost`. Passing it as
  `expected_margin_lyd` charged the campaign twice.
- **Open the screen.** Two of the five were found by loading a page in a
  browser and reading it. Neither was findable from pytest.

---

## 8. Session log

### 2026-09-18 · Session 1 — scaffold

- Read the SIC proposal (v2, 984 lines) and the parent platform proposal.
- Audited the machine: found Python 3.14/3.10 but no 3.11; git, Docker and
  gh missing at the time.
- Built the repository skeleton at `D:\Sic`: 182 files, 63 directories, laid out
  by the proposal's nine architectural layers.
- Wrote for real: `config.py`, `api/schemas.py`, `api/main.py`,
  `decision/guardrails.py`, and the test suite.
- Wrote ~85 documented stubs covering ingest, synthesis, features, M1–M6 and
  the rest of the decision layer.
- Wrote docs: architecture, data dictionary, syllabus coverage matrix, setup,
  7 model-card stubs, 4 ADRs, `data/README.md`.
- Verified: all Python parses, all YAML parses, all internal doc links resolve.

### 2026-09-18 · Session 2 — branch split, datasets, handover

- Confirmed git / gh / Docker were installed, in non-standard locations
  (`D:\Git`, `D:\GITHUB_CLI`, `%LOCALAPPDATA%\Programs\DockerDesktop`).
- **Scoped the repo down to `ali_branch`** — CVM only:
  - Moved all M7 Copilot code to `docs/integration/copilot_starter/` with a
    README explaining what to keep and what to discard.
  - Replaced `/v1/copilot/ask` with **`/v1/cohort/query`** — the integration
    endpoint other components actually need.
  - Removed the copilot container, the `copilot` dependency extra, the config,
    and the `copilot` task from `tasks.ps1` / `Makefile`.
  - Amended ADR 0004 rather than rewriting it: the no-write-path decision
    *strengthened* when the agent moved out of process.
- Wrote [`docs/INTEGRATION.md`](docs/INTEGRATION.md) — the full contract for
  Components 2, 4 and 5, with a worked example for the Copilot's flagship
  question.
- Researched and verified five additional free datasets (Criteo Uplift,
  Hillstrom, KKBox, Milan CDR, UCI Online Retail II), plus three more Arabic
  corpora. Added them to `conf/data.yaml` (disabled by default) and
  `scripts/download_data.py`, with disk-budget guidance.
- Initialised git on branch `ali_branch`.
- Wrote this file and [`docs/TESTING.md`](docs/TESTING.md).

### 2026-09-18 · Session 3 — scope down to four modules

- **Removed M5 (network AutoEncoder) and M6 (Arabic care text) entirely.**
  Deleted the packages, configs, routers, model cards, notebook folders and the
  two Command Center screens (Network Risk Map, Voice of Customer). The
  `/v1/network/site-risk` and `/v1/text/classify` endpoints are gone from the
  published contract.
  - M1 now takes **raw per-cell quality signals** as features
    (`dropped_call_rate_30d`, `data_session_failure_rate`,
    `cell_outage_hours_30d`) rather than a modelled degradation score. Those
    come from Component 2 once it exists; until then the synthesis engine
    generates them. Contract: `docs/INTEGRATION.md` §6.
  - Care **volume** (`care_contacts_30d`) survives as a feature; care **text**
    does not.
  - OpenCelliD stayed at this point, for district context. Removed in 3d.
  - Dependencies: `nlp` extra replaced by `rtl` (arabic-reshaper +
    python-bidi only). Arabic RTL rendering is still needed for offer copy in
    the channel simulator.
- **Removed all syllabus-chapter tracking.** Deleted
  `docs/syllabus_coverage.md`; stripped chapter annotations from 44 places
  across docstrings, config comments, model cards, templates, CONTRIBUTING and
  the PR checklist.
- Verified the installed toolchain: git 2.55.0 (`D:\Git`), gh 2.101.0
  (`D:\GITHUB_CLI`), Docker 29.8.0 (`%LOCALAPPDATA%\Programs\DockerDesktop`).
  All present; PATH needs a new shell to see them.
- Wrote [`conf/market.yaml`](conf/market.yaml) and
  [`docs/MARKET_QUESTIONS.md`](docs/MARKET_QUESTIONS.md) — every domain fact the
  synthesis engine needs, pre-filled with clearly-labelled assumptions so they
  can be corrected rather than authored from scratch.

### 2026-09-18 · Session 3b — operator switched to Almadar Aljadid

Real operator data supplied: `Almadar/internet_offers_data_v4.csv`,
`Almadar/translated_service_details.md`,
`Almadar/translated_internet_service_details.md`.

- **Operator is now Almadar Aljadid (MNC 01), not Libyana (MNC 00).** Updated
  `conf/config.yaml`, the OpenCelliD filter (`mnc: ["01"]` only), the Pandera
  contract, the UI caption, and every doc reference. Libyana remains only as
  the competitor dual-SIM leakage flows toward.
- **Wrote [`conf/catalogue.yaml`](conf/catalogue.yaml)** — the bundles
  structured from the CSV, plus both emergency-credit
  products. `variable_cost_lyd` is an estimate throughout and flagged as one.
- **Recharge ladder confirmed: 3 / 5 / 10 / 20 / 40 / 100 LYD.** Propagated to
  `conf/market.yaml` and the quantile mapping in `conf/data.yaml`.
- **Rewrote `conf/advance.yaml` entirely** for the two real products and the
  new argument. Added an `affordability_ceiling` guard (never advance more than
  one modal top-up can clear) and replaced `line_reset_risk` with
  `lockout_risk`, which is what is actually measurable for this operator.
- **Off-peak is the morning, not the night.** `SABAH_1` is the anchor product;
  the fallback window moved from 01:00–06:00 to 06:00–11:00. Renamed the
  guardrail key `require_additive_night_pack` → `require_additive_offpeak_pack`
  in both the config and `guardrails.py`.
- Reworked the M4 module docstrings, `synthesis/overlays.py` (added
  `apply_emergency_credit_behaviour` and `apply_morning_offpeak_usage`), and
  the M4 section of the data dictionary.
- Updated `docs/MARKET_QUESTIONS.md`: 4 of 10 questions now confirmed. Q2
  (pay-as-you-go tariffs) is the remaining blocker.

**Note on `docs/proposal/`.** Rewritten in session 3e to describe the project
as it now stands: Almadar, four modules, the real catalogue and tariffs, and the
integration contract. It is written as a standalone proposal with no changelog
framing, so it reads as the specification rather than a diff. Where it and the
configs disagree, the configs win -- they are what the code reads.

---

### 2026-09-18 · Session 3c — market answers applied

`Almadar/Pay-as-you-go tariffs.md` supplied. Confirmed and applied:

- **PAYG tariffs (Q2).** On-net voice is a **3-minute block at 0.090 LYD then
  0.050/min**, not a flat rate — so call length drives revenue per minute and
  the generator must produce realistic call lengths. Off-net 0.090/min,
  landline 0.040/min. SMS **0.050 either direction** — no on-net discount, so
  SMS carries no pricing signal; `conf/features.yaml` now excludes SMS on/off-net
  mix by name with the reason. Data (Bjawak) 0.025/MB = **~25x the bundle
  rate**, which promotes `bundle_vs_payg_share` from a ratio to a targeting
  feature. International voice is not published and is left null, not guessed.
- **Q3b.** `نت ساعة 1_5G` / `نت ساعتين 2_5G` are unlimited within the hour.
  `variable_cost_lyd` stays an estimate by decision — label it, do not remove it.
- **Q5.** No zero-rated apps.
- **Q7.** ARPU **12 -> 30 LYD**, dual-SIM **60% -> 85%**. The ARPU fix resolves a
  real inconsistency (cheapest monthly bundle is 20 LYD). It rescales the
  business case: revenue at risk ~420k -> **~1.05M LYD/month**, CLV ceiling
  ~21 -> **~54 LYD**. Dual-SIM at 85% makes `incoming_outgoing_ratio` the
  central churn feature rather than a clever extra.
- **Q8 partial.** Ramadan seasonality **removed** — needs per-year dates and the
  effect was a large guess. Salary days 25-30 and evening peak 19:00-22:00 kept
  as labelled assumptions.
- **Q10.** MSA for all customer-facing copy.

**Two decisions still open, with recommendations in MARKET_QUESTIONS.md:**

1. **Weekend days — recommend keeping**, minimally. Friday–Saturday is a public
   fact rather than a guess, it costs one derived boolean, and removing weekly
   rhythm from the daily sequences quietly handicaps the M1 LSTM arm against
   LightGBM through a data-generation choice. No usage multiplier — that would
   be the guessed part.
2. **Geography — recommend splitting the question.** Remove the geography layer
   (district, OpenCelliD, per-cell troughs): with M5 gone it has no consumer,
   and `district` survived only to be forbidden by the fairness guardrail.
   But **keep network quality as a subscriber-level feature** — UCI has a real
   `Call Failures` column and Cell2Cell has `dropvce`/`blckvce`/`unansvce`, so
   it is measured signal, not an invented Libyan field. If geography goes, the
   redlining audit should be replaced by a discount-distribution audit across
   value deciles and tenure bands, which is auditable with data we have.

### 2026-09-18 · Session 3d — weekend kept, geography dropped

**Weekend days kept**, per the recommendation. `conf/market.yaml#weekend_days`
is now `confirmed` (Friday-Saturday is a public fact, not an estimate) with
`apply_usage_multiplier: false` -- the flag only, no guessed effect. Added an
`is_weekend` feature family and `sequences.require_weekly_periodicity: true`,
because generated daily series with no weekly rhythm would handicap the M1
LSTM arm through a data-generation choice rather than on merit.

**Geography dropped entirely.** No districts, cells, coordinates, OpenCelliD or
per-cell trough detection.

- Deleted `src/cvm/ingest/opencellid.py` and its Pandera contract.
- Dataset D (OpenCelliD) and dataset I (Milan CDR) removed from
  `conf/data.yaml`, `scripts/download_data.py` and `data/README.md`. Milan's
  only purpose was real per-cell load curves, which nothing needs now.
- `OPENCELLID_API_KEY` gone from `.env.example` and `config.py`.
- `district` and `home_cell_id` removed from `SubscriberProfile` and
  `CohortFilter`. A caller passing `district` now gets a 422 rather than a
  silently-ignored field, with a test asserting it.
- M3 uses ONE national off-peak window -- the operator's published
  06:00-11:00 -- instead of detecting troughs. `detect_trough` replaced by
  `offpeak_window()`.
- `cell_outage_hours_30d` renamed `service_outage_hours_30d`; network quality
  is now `level: subscriber` with no cell join and no load curve.

**Fairness guardrail reworked.** The redlining audit went with geography --
auditing a dimension we no longer model would be theatre. `audit_redlining`
is replaced by `audit_distribution(mean_by_group, dimension)` across
**value deciles and tenure bands**, which asks a real question: are we
systematically giving less to low-value or newer subscribers? `district` stays
on `forbidden_pricing_features` so reintroducing geography cannot silently make
it a price lever.

**Defect found and fixed while renaming (worth knowing about).**
`tests/leakage/test_point_in_time.py` asserted that every field in
`hazard.LABEL_GENERATING_FIELDS` appeared in `excluded_columns`. It did not,
so **that test would have failed on the first real pytest run** -- and
"fixing" it by excluding those fields would have been much worse, because they
are the hazard's behavioural *drivers*. Excluding them leaves the model nothing
to learn and every metric collapses for a reason nobody could find.

Resolved by splitting the concept in `hazard.py`:

- `LABEL_DRIVER_FIELDS` -- behavioural inputs to the hazard. These **stay**
  available as features. Recoverable signal is the whole point.
- `LABEL_ARTIFACT_FIELDS` -- `hazard_score`, `churn_date`, the label itself,
  `days_to_churn`. These must **never** reach the feature matrix, and
  `excluded_columns` is now a superset of them.

`tests/leakage/` asserts both directions and that the two sets are disjoint.
`docs/architecture.md#label-generation` explains why the driver overlap is
honest rather than circular, which is the paragraph the report needs.

**Verified:** all Python compiles, all YAML parses, all doc links resolve,
31/31 config-level assertions pass, and 16/16 guardrail functions behave
correctly when executed directly (including the new distribution audit).

### 2026-09-18 · Session 3e — proposal rewritten

`docs/proposal/AI_CVM_Suite_SIC_Proposal_v2.md` rewritten from scratch as a
standalone specification. ~13,900 words, no changelog framing -- it reads as
the proposal rather than as a record of revisions.

Reflects the project as it actually is: Almadar Aljadid, four modules, the real
real catalogue and published tariffs, subscriber-level service quality, no
geography, the integration contract, and the emergency-credit argument built on
the 3 LYD card versus 5 LYD debt.

Three parts are new analysis rather than restatement, and they are the strongest
material in the document:

1. **The cannibalisation break-even (§7.2).** A 1 LYD unlimited morning pass
   against the 20-80 LYD monthly ladder means cannibalisation, not incentive
   spend, is what decides the business case. Above **~2.2% downgrade rate on the
   treated cohort the entire retention gain disappears** -- which is why
   `max_simulated_arpu_erosion` sits at 2%, just below break-even. The
   sensitivity table in §7.1 has no loss-making cell and the document says so
   explicitly rather than manufacturing one.
2. **Prevented service lockouts (§7.4).** The full assumption chain from
   150k monthly emergency-credit users down to ~168k LYD/month recoverable,
   every step labelled.
3. **The label driver / artifact distinction as a pitch answer (§8.3).** "How
   can you train on a label you generated yourself?" now has a prepared answer
   that explains the recoverable-signal design instead of deflecting.

Business case rescaled throughout for ARPU 30: revenue at risk ~1.05M LYD/month,
ROI ~6.0x at a 1.5 LYD blended incentive, ~1.32M LYD/month in avoided waste.

### 2026-09-18 · Session 3f — Mix removed, Cell2Cell grounded

**Mix tiers removed entirely.** Five families (Diamond / Platinum / Gold /
Silver / Bronze) and 20 bundles deleted from `conf/catalogue.yaml`. The
catalogue is now **37 bundles across 12 families**; meta counts updated and
asserted.

Two consequences handled rather than glossed over:

- **The 35 LYD cannibalisation anchor survives.** عروض شهرية `نت 20`
  (`MO_20`) is 35 LYD for 20 GB over 30 days, so the §7.2 break-even arithmetic
  (34 LYD/month lost per downgrader, ~2.2% of cohort wipes out the gain) carries
  over unchanged. Prose re-anchored from "Mix tiers" to the monthly ladder.
- **Voice instruments thinned.** Mix was the main data+voice family. Only the
  morning pass (unlimited voice) and the shared Family plans now carry minutes
  at all, which makes the morning pass the primary **voice** instrument as well
  as the off-peak data one. `conf/pricing.yaml` tier instruments updated
  accordingly: Gold -> `morning_pass`, Platinum ->
  `morning_pass_plus_volume_upgrade`. The loyalty ladder now maps onto the
  monthly volume ladder (6/10/20/40/80 GB) and the Golden-vs-Silver quality
  ladder instead of named product tiers.

**Cell2Cell registered as a local two-file source** at
`data/raw/telecom/telecom` — `Client.csv` (100,000 × 50) and `Record.csv`
(100,000 × 51), joined 1:1 on `Customer_ID`, join verified complete. This is the
original Duke distribution rather than a preprocessed single-table cut, and that
matters: **it keeps placed and received voice as separate columns, and peak and
off-peak minutes as separate columns.** Condensed versions collapse both.

**What it grounds.** Two features carry most of the project's differentiation
and were previously generated with no empirical reference at all:

| Feature | Columns | Measured |
|---|---|---|
| `incoming_outgoing_ratio` | `recv_vce_Mean` / `plcd_vce_Mean` | median 0.280, p10 0.052, p90 0.681 |
| `offpeak_data_ratio` | `mou_opkv_Mean` / total | median off-peak share 0.424 |
| `revenue_decay_ratio` | `avg3mou` / `avg6mou` | median 1.012, 46.8% declining |

Both leakage columns are 0% null across all 100,000 rows. Marked `mapped` rather
than `gen` in the data dictionary, with the distributions recorded so the
overlays fit against them.

Also usable: `inonemin_Mean` (short-call share — relevant because Almadar bills
on-net voice as a 3-minute block), data-side failures, care-contact volume,
`months` tenure, `roam_Mean`, `uniqsubs`/`actvsubs`.

**Three caveats, all recorded in config and docs rather than just noted here:**

1. **The label prevalence is unusable.** Balanced at ~49.6%. Calibrating on it
   would calibrate to a 50% prior and silently destroy the claim that a 0.31
   means 31%. `use_label_prevalence: false`,
   `require_prior_correction: true`, and `assert_prior_corrected()` in the
   loader to make it fail loudly rather than quietly.
2. **The leakage ratio does not predict churn in this data** — 0.282 for
   non-churners against 0.278 for churners. Expected, because it is a
   single-SIM postpaid market with no receiving-SIM behaviour to detect. The
   source grounds the feature's *distribution*, not its *predictive power*, and
   only 3.0% exceed a ratio of 1.0 — which at 85% dual-SIM penetration is the
   baseline to **deviate from**, not reproduce. Added as a prepared answer in
   the proposal's evaluator-questions table rather than buried.
3. **22 columns dropped at the ingestion boundary** — US household marketing
   data: ethnicity, marital status, income, five child-age brackets, dwelling
   type and size, vehicle counts, credit-card flag, US area. A Libyan prepaid
   operator holds none of it and several are protected or proxy-protected.
   Dropped at ingestion rather than merely excluded from pricing, and
   `FORBIDDEN_COLUMNS` is duplicated in the loader so a direct caller cannot
   bypass the config.

**Verified:** Python compiles, YAML parses, all doc links resolve, catalogue
counts self-consistent, and 8/8 guardrail checks pass against surviving bundles
(including `MO_20` at 10% off and the 1 LYD morning pass).

### 2026-09-18 · Session 3g — uplift promoted, proposal halved

**Restructured around the stated objective:** predict churn -> understand value
-> estimate treatment effect -> decide whether to intervene.

The misalignment was that **uplift had no module**. `uplift.py` sat buried in
the decision package and the module table did not mention it, even though
"identify who can actually be influenced" is a first-class step in the pipeline.
Meanwhile M3 was framed as "which of N bundles" — merchandising-forward rather
than decision-forward.

| Before | After |
|---|---|
| M3 = Dynamic Pricing | **M3 = Uplift Engine** (`models/m3_uplift/`) |
| uplift buried in `decision/uplift.py` | promoted to its own module with its own config |
| pricing was a numbered module | pricing is what the **Decision Engine** does with M1-M4 |
| catalogue framed as the thing being optimised | catalogue is the **action space + cost model** |

Moves: `decision/uplift.py` -> `models/m3_uplift/two_model.py`;
`decision/m3_pricing.py` -> `decision/pricing.py`; new
`models/m3_uplift/evaluate.py` (Qini, uplift@k, quadrant counts,
`validate_on_criteo`, `expected_value_of_treatment`); new
`conf/models/m3_uplift.yaml`; uplift block removed from `conf/pricing.yaml`,
which now opens with an `action_space` block instead.

Two things made explicit that were implicit before:

- **`E[gain] = uplift x CLV - offer_cost`** is now the stated first question of
  the decision engine. A negative value means do not treat *regardless of how
  high the churn score is*.
- **"No action" is a first-class outcome**, and `include_no_action: true` makes
  it a real candidate in the action space rather than a fallthrough.

`forbid_synthetic_offers: true` records why the catalogue is not optional: an
invented offer has an invented cost, which would make the margin floor enforce
one made-up number against another. Two of the six things this system does
— "is this offer worthwhile" and "recommend the best action" — cannot be
answered without a real action space.

**Proposal rewritten smaller:** 1,628 lines / 13,900 words -> **714 lines /
5,494 words**, restructured so section 2 *is* the pipeline. Cut the exhaustive
field tables (they live in `data_dictionary.md`), the full catalogue table
(`catalogue.yaml`), the long execution plan, and half the evaluator Q&A. Kept
every substantive finding: the 3-vs-5 LYD lockout, the 2.2% cannibalisation
break-even with the ARPU-invariance proof, the driver/artifact distinction, the
leakage-grounding caveat, and the Criteo validation.

Added to the Q&A: *"Why does the catalogue matter if you could invent offers?"*
— because it will be asked now that the catalogue is visibly demoted.

**Verified:** Python compiles, YAML parses, all doc links resolve, no stale
`m3_pricing` / `decision.uplift` references, and 22/22 checks pass through the
real config loader and guardrail functions.

### 2026-09-18 · Session 3h — 5 LYD floor, one arm, ARPU 40, ladder cannibalisation

Four changes from the project owner, two of which moved load-bearing arguments.

**1. The smallest recharge card is 5 LYD, not 3.** Ladder is now
`[5, 10, 20, 40, 100]`; weights renormalised to `[0.54, 0.21, 0.13, 0.08, 0.04]`
with the old 3 LYD share folded into the 5.

This **invalidated the M4 headline finding** and replaced it with a different
one. The old argument was arithmetic impossibility: a 3 LYD card cannot clear a
5 LYD data advance, so the debt persists and the subscriber is locked out. With
a 5 LYD floor the debt *is* clearable — exactly, to the dinar — so the new
argument is a **zero residual**: clearing consumes the entire minimum top-up and
hands the subscriber back a zero balance. They paid five dinars for nothing, so
the rational move is not to pay it, and a deferred recharge on a prepaid line is
where silent churn starts.

**This is weaker evidence and the repo says so.** `conf/advance.yaml` carries an
explicit honesty note; `debt_exceeds_smallest_card` is kept as `false` rather
than deleted, so a reader who remembers the old claim sees it was retired.
A new test asserts the equality *and* that the retired claim stays false.

Secondary finding, now recorded: a 1 or 3 LYD **airtime** advance still leaves
change off the smallest card, so only the 5 LYD data advance has the
zero-residual problem. That is a reason to prefer the small rungs, and it is
tested.

**2. The sequence arm is gone.** M1 is one model family: LightGBM primary,
XGBoost/CatBoost challengers, five classical baselines — eight algorithms, one
temporal split, calibration curves for all of them. Deleted `arm_b_lstm.py`,
`features/sequences.py`, the LSTM model card, the `dl` extra, the TensorFlow
seeding branch, the whole Colab section of `docs/setup.md`, and the sequence
tensors from the architecture diagram and feature store. `arm_a_lightgbm.py` →
`gradient_boosting.py`, since "Arm A" means nothing without an Arm B.

**API contract change, documented in INTEGRATION.md §"One contract change since
the freeze":** `/v1/score/churn` no longer accepts `arm`, and
`/v1/subscriber/{id}` no longer returns `lstm_churn_probability`. Both selected
between options that no longer exist. `extra="forbid"` means a caller still
sending `arm` gets a 422 naming the field, not silent acceptance.

**3. ARPU 30 → 40, blended incentive 1.5 → 5 LYD.** The incentive change is the
consequential one. Business case rebuilt:

| | |
|---|---|
| 12-month value per subscriber | **480 LYD** |
| CLV ceiling (15%) | **72 LYD** (was 54) |
| Revenue at risk | **1.4M LYD/month** |
| Campaign cost @ 5 LYD × 120k | **600,000 LYD** |
| ROI at 2.5 pp uplift | **2.4×** (was 6.0×) |

**The ROI table now has loss-making cells, which is the improvement.** At a
5 LYD incentive against 480 LYD of annual value, break-even is
`5 / 480 = 1.04 pp` of uplift — so the programme does not hinge on the churn
model being excellent, it hinges on M3 clearing one percentage point of genuine
uplift. That is a far more demanding claim and the holdout exists to measure it.
The same number is now stated in §2.4 of the proposal, in `m3_uplift.yaml`'s
expected-value formula, and in the README principles table.

§6.3 was rewritten: the honest counterfactual is **targeting on churn score
alone**, not a blanket campaign, and we deliberately refuse to quote a quadrant
mix we have not measured.

**4. Cannibalisation re-based on the ladder.** The owner's domain correction:
نت 20 at 35 LYD is the *base* monthly — you need it for all-day data regardless
of free mornings — so the 1 LYD pass cannot displace it. It displaces the
bundles *above* it.

This does not remove the risk, it relocates it, and the relocation makes the
guard better. It is now **mechanistic rather than statistical**: it keys on
`current_monthly_bundle_lyd`, the exposure itself, where risk × value was only
ever a proxy for "probably on a big bundle". Subscribers on or below the base —
and those with no monthly bundle — are structurally immune and now get offers
the old guard withheld.

Break-even moved from a single 2.2% to a range, because the loss is the gap
between rungs rather than the whole bundle:

| Downgrade path | Monthly loss | Break-even |
|---|---|---|
| نت 40 → نت 20 + pass | 14 LYD | 7.1% |
| نت 80 → نت 20 + pass | 44 LYD | 2.3% |

The 2% cap is unchanged — it sits below the **worst** case rather than being
retuned to the best one. The ARPU-invariance proof from session 3f is retired
with the single-anchor model it belonged to.

**Fixed in passing (pre-existing, unrelated):**

- `tests/unit/test_schemas.py` imported `TextClassifyRequest`, deleted with M6
  in session 3. Collection error — the whole unit suite could not run.
- **The MSISDN privacy scan was failing on its own fixtures.** Three test files
  contain `0912345678` as the number we assert gets *rejected*, and both the
  pytest check and the CI job flagged them. Added a per-**line** `msisdn-fixture`
  marker rather than exempting `tests/`, so the scan stays repository-wide and
  every exemption is visible where a reviewer reads it. Both checks now clean.

**Verified:** 78 pytest tests pass (5 xfail, 0 fail), plus 64 standalone checks
through the real config loader and the real guardrail functions — every ROI
cell, every break-even share, and every exemption branch computed rather than
asserted. YAML parses, Python compiles, CI scan simulated clean.

---

### 2026-09-18 · Session 4 — phase 1 complete, ingestion runs

Layer 1 is at **100%** and the project at **41%** (108 stub functions left, from
121). `python scripts/progress.py` prints the burn-down.

**Built:** `hashing.py`, `uci_iranian.py`, `cell2cell.py`, `ibm_telco.py`,
`run.py`, plus three new loaders the repo previously only *named* —
`criteo_uplift.py`, `hillstrom.py`, `online_retail.py`. `python -m
cvm.ingest.run` lands A/B/C as Parquet and probes F/G/J, printing a table and
exiting non-zero if any source fails.

**Two proposal claims verified against the actual files.** UCI has *exactly*
300 duplicates (9.52%), and Cell2Cell's medians are 0.280 and 0.424 — as
quoted, to three decimals.

**One claim was mislabelled.** The decay figure (median 1.012, 46.8% declining)
comes from `avg3mou / avg6mou` — minutes — but was attached to a feature named
`revenue_decay_ratio`. Measured separately they disagree: minutes 1.012/46.8%,
revenue 1.000/42.2%. Usage turns down before spend does, which is the whole
reason a decay ratio is an early warning, so generating one and labelling it the
other would have flattened the signal. Both now exist and are named correctly.

**Six things bit, and four will bite again:**

| | |
|---|---|
| `sklift.datasets.fetch_criteo` | **Dead — 403.** Criteo's own `go.criteo.net` link 404s too. Fetches from HuggingFace directly now: 311 MB once, then a seeded 10% sample taken *during* a chunked read. |
| `ucimlrepo` for dataset 502 | **Cannot fetch it** — it is a two-sheet Excel workbook. Static archive instead, and **both** sheets: one sheet is half the period and biases BG/NBD toward short lifetimes. |
| Criteo's `conversion` + `exposure` | **Post-treatment, and the first loader passed both in as features.** `conversion` is downstream of `visit`; `exposure` is decided after assignment and conditioning on it breaks the randomisation. Both dropped, with an assertion. |
| `openpyxl` | Undeclared. Dataset C is `.xlsx`. Now a core dependency. |
| IBM Telco's columns | Carries Gender, Senior Citizen, Partner, Dependents **and** street-level lat/long. 12 columns dropped at the boundary, same treatment as Cell2Cell's 22. |
| The MSISDN scanner | Two real gaps and one false positive — see below. |

**The privacy scanner was weaker than it looked.** It missed the international
spelling (`+218` drops the trunk zero) and grouped digits (`091 234 5678`), and
it matched *inside its own SHA-256 digests*, because a 64-char hex string often
contains `094` followed by seven numeric characters — so whether the scan passed
depended on the salt. All three fixed. `tests/unit/test_privacy.py` now imports
the pattern instead of re-spelling it, and locks in 8 real formats, 7
non-numbers and 1,200 digests.

**Verified:** 131 tests pass (9 xfail, from 10 — `test_uci_duplicate_rows_are_dropped`
is green, and a second leaky-field test joined it), ruff and black clean.

---

### 2026-09-19 · Sessions 5–9 — phases 4 to 10

Built out every remaining layer, one phase at a time, each ending in a full
verification and a commit. The roadmap carries the detail; the findings worth
knowing before touching a model:

- **LightGBM built one tree.** It tracks `binary_logloss` alongside the
  requested metric and early stopping watches all of them; `scale_pos_weight≈27`
  degrades logloss from iteration 1. PR-AUC 0.3076 → 0.4556 once `metric` was
  set on the constructor. A hard failure under 3 trees now guards it.
- **In-sample concordance reversed the survival conclusion.** RSF 0.8937
  in-sample → 0.8292 held out; Cox 0.8534. The forest's win was memorisation.
- **M3 trained and scored the same rows.** Qini 0.2745 and uplift@30% +50.8pp
  became 0.0091 and +4.9pp held out.
- **Qini normalisation was ~3× too large** — divided by the endpoint rather
  than Radcliffe. Now agrees with scikit-uplift to 3.1e-05.
- **`sample_weight` passed to LightGBM's constructor is silently discarded.**
  Mean p 0.504 vs 0.950. `train` now takes it explicitly and raises on other
  fit-only params.
- **The M4 calibrator was fitted on fuzzy inferred labels**, which are ~50/50
  by construction, so isotonic sent every score to 0.5 — and it was being
  reported as a bias correction.
- **BG/NBD with penalizer 0.01 broke the fit**: b=0.570 gives a U-shaped
  dropout Beta and 844 NaN of 4,933. Default is 0.0 now.
- **Spearman over sorted quantiles is always exactly 1.000.** Removed from the
  IBM benchmark rather than reported as agreement.
- **Four redundant feature columns** — two exact duplicates, two affine.
- **454 MB of NVIDIA CUDA in a CPU-only image**: `xgboost` declares
  `nvidia-nccl-cu12` unconditionally on Linux. A `serve` extra halved both
  images.

### 2026-09-19 · Session 10 — five bugs a green suite could not see

Asked to make the system testable by hand, and found that nothing in eleven
phases had ever scored one real subscriber through the running container or
opened a screen in a browser. Five faults were waiting on those two paths.

Three needed a **one-row batch**: the sklearn version skew that 500'd
`/v1/score/churn`, the NaN median that produced `INT64_MIN` for
`time_to_churn_days`, and the SHAP background that made every contribution
exactly zero. Two needed a **running container**: the object-dtype transpose
that meant the Subscriber 360 waterfall had never rendered, and the read-only
mount that killed the offer panel.

Then the Campaign Builder's blanket comparison turned out to be measuring the
campaign against itself, charging the campaign cost twice, testing viability
gross, and clipping away the negatives that were the whole point. Fixing it
exposed a flaw in the fix's own headline — an unconstrained blanket arm against
a budget-capped targeted one measures the budget, not the targeting — so there
are now two comparisons and the screen leads with the one that holds spend
constant.

**Verified:** 368 tests pass with zero xfail (from 349), 85 phase checks pass
with none failed and none pending, ruff and black clean, all six surfaces
exercised in the container by hand.

**Pushed** to `ItsSp00ky/LoopGain-Telecom-AI` as `Ali_Branch` — the first time
anything in this branch has left the machine, and the last PENDING check in the
project.

**A correction recorded in the roadmap:** the blank SHAP waterfall was first
attributed to the zero-background bug. That bug is real and was measured on the
API, but the screen never reached it — the dtype fault was in front. Both the
roadmap and the commit say so.

---

## 9. How to update this file

Append a dated entry to §8 at the end of every working session, and update §2
and §6 so they describe the *current* state rather than the history. Keep
entries factual: what changed, what was decided, what broke.

If you are an AI session picking this up: read this file, then
`docs/INTEGRATION.md` if the work touches the API, then the specific module's
docstring. Do not re-derive decisions already recorded in §3 — challenge them
explicitly if you disagree, but do not silently reverse them.
