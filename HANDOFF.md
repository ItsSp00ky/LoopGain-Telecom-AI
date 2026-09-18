# HANDOFF

**Read this first if you are picking up this project** — whether you are a new
AI session, a teammate, or me in three weeks having forgotten everything.

Last updated: **2026-09-18** (session 3c)
Branch: **`ali_branch`** · Repo root: `D:\Sic` · Owner: **Ali**

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

**The repository is scaffolded and the skeleton runs; no model has been trained
and no data has been downloaded.** Committed on `ali_branch` (`21e7c09` is the
root commit), no remote yet. The config system, the API contracts, the FastAPI app and the
complete pricing-guardrail engine are *written and working*. Everything else is
a documented stub that raises `NotImplementedError` — each file carries its
module number, its owner, and a docstring explaining what it must do and why.
About 60 tests pass today; they cover config loading, privacy invariants, API
contracts and all six pricing guardrails.

**Scope is four modules:** M1 churn, M2 value/CLV, M3 pricing, M4 advance.
Network anomaly detection, care-text classification and the Employee Copilot
all belong to other components.

**Operator is Almadar Aljadid (المدار الجديد), MCC/MNC 606-01** — not Libyana.
Real catalogue data is in hand: 37 bundles across 12 families, the confirmed recharge ladder, and
both emergency-credit products. See §3a below for what that invalidated.

**No blockers, and no open scope questions.** All ten market questions in
[`docs/MARKET_QUESTIONS.md`](docs/MARKET_QUESTIONS.md) are resolved: eight
confirmed from operator documentation, one a labelled estimate (base and
economics), and the two scope calls decided in session 3d. One minor factual
gap remains (Q6b, partial-recharge settlement) and it does not block anything.

**No geography anywhere.** No districts, cells, coordinates or OpenCelliD.
Network quality survives as a subscriber-level feature because it is real
measured signal, not an invented Libyan field.

**Catalogue is 37 bundles across 12 families** (Mix removed). The morning pass
is now the primary voice instrument as well as the off-peak data one, since only
it and the Family plans carry minutes.

**Cell2Cell is supplied locally** at `data/raw/telecom/telecom` as the original
two-file Duke distribution, and it grounds the leakage and off-peak features
against measured distributions. Three caveats travel with it -- see session 3f.

---

## 3. Decisions already taken (do not re-litigate without reason)

| # | Decision | Why |
|---|---|---|
| 1 | **Repo root is `D:\Sic`**, branch `ali_branch` | Working directory when the project started. The GitHub repo name does not have to match the folder. |
| 2 | **Python 3.11, via conda** | TensorFlow, scikit-survival and SDV have no wheels for 3.12+. Machine has 3.14 and 3.10 in base — neither works. |
| 3 | **M7 Employee Copilot removed from this branch** | It is Component 5, owned by a teammate. Its scaffolding was written and moved to [`docs/integration/copilot_starter/`](docs/integration/copilot_starter/) as a handover, not deleted. |
| 4 | **LangChain / Chroma / sentence-transformers dropped** | Consequence of #3. Saves ~2.5 GB of install on a machine with ~20 GB free. |
| 5 | **M5 (network AutoEncoder) and M6 (Arabic care text) removed entirely** | Session 3. Network modelling is Component 2; care text is Component 4. Building either here would duplicate a teammate's work. M1 consumes subscriber-level quality signals — dropped-call rate, outage hours — as ordinary churn features instead. Contract in [`docs/INTEGRATION.md`](docs/INTEGRATION.md) §6. |
| 5a | **Geography removed entirely; network quality kept** | Session 3d. No districts, cells, coordinates or OpenCelliD — with M5 gone, geography had no consumer, and `district` survived only to be forbidden by the fairness guardrail. Network quality stays because it is *real measured signal* (UCI `Call Failures`, Cell2Cell `dropvce`), just subscriber-level rather than cell-level. The redlining audit was replaced by a value-decile / tenure-band distribution audit. |
| 5b | **Weekend days kept, deliberately** | Session 3d. Friday–Saturday is a public fact, not an estimate, and it costs one derived boolean. Removing weekly rhythm from the daily sequences would handicap the M1 LSTM arm through a data-generation choice rather than on merit. No usage multiplier — that would be the guessed part. |
| 6 | **All syllabus-chapter tracking removed** | Session 3. `docs/syllabus_coverage.md` deleted; chapter annotations stripped from every docstring, config comment, model card and template. Coverage is no longer a project constraint, so the annotations were noise that would drift. |
| 7 | **Other components integrate over HTTP, never by import** | Four reasons in [`docs/INTEGRATION.md`](docs/INTEGRATION.md) §1: the feature store will be replaced at scale, importers bypass guardrails, importers skip the audit log, independent deploys. |
| 8 | **Guardrail thresholds live in `conf/*.yaml`, never in code** | An evaluator will ask to change one live during the demo. |
| 9 | **Five recommended datasets added beyond the proposal** | Criteo Uplift in particular: it is the only real treatment/control data available, and without it the uplift model in M3 cannot be honestly validated. See `data/README.md`. |

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
| **A 5 LYD debt exceeds the 3 LYD smallest recharge card** — a small-card recharger cannot clear it in one top-up, and unpaid debt blocks re-subscription, locking them out of the service they reached for | ladder + product price |
| The two products are mutually exclusive, so distressed subscribers alternate between them — unmonitored | both FAQs |

**Two other changes from the real data:**

- **The off-peak window is the MORNING.** عروض الصبح is 1 LYD for unlimited
  data *and* voice, 06:00–11:00. Not a night bundle. This is good news: M3
  personalises a product that exists, and the operator has already told us when
  its spare capacity is. It also sharpens the cannibalisation guard, because
  06:00–11:00 is real usage time for commuters.
- **ARPU was wrong and is now fixed.** The inherited 12 LYD/month was
  inconsistent with a catalogue whose cheapest monthly bundle is 20 LYD.
  Revised to **30 LYD**, which rescales the business case: revenue at risk
  ~420k -> **~1.05M LYD/month**, CLV ceiling ~21 -> **~54 LYD** per subscriber.
  Any figure carried over from the old proposal needs recomputing.

---

## 4. What is real vs. what is a stub

### Written and working

| File | What it does |
|---|---|
| [`src/cvm/config.py`](src/cvm/config.py) | Env + YAML loader, `guardrail()` accessor that raises on a typo'd path, `seed_everything()`, salt enforcement |
| [`src/cvm/api/schemas.py`](src/cvm/api/schemas.py) | Every Pydantic v2 request/response contract. **Frozen** — changing one is a cross-team event |
| [`src/cvm/api/main.py`](src/cvm/api/main.py) | FastAPI app: lifespan, request-id + latency middleware, structured errors. Boots, `/docs` works |
| [`src/cvm/decision/guardrails.py`](src/cvm/decision/guardrails.py) | **All six pricing guardrails, fully implemented** — margin floor, CLV ceiling, budget, cannibalisation, fairness + distribution audit, tier ceiling |
| [`tests/`](tests/) | ~60 passing tests: config, privacy, schemas, all six guardrails, API contracts, plus config-level leakage and credit-safety assertions |
| `conf/*.yaml` | Every threshold, weight, tier boundary and safety guard |
| `docker/`, `docker-compose.yml`, `.github/workflows/ci.yml` | Four-service stack; CI with separate required jobs for leakage and guardrails |

### Stubbed — raises `NotImplementedError`, docstring explains the contract

Everything under `ingest/`, `synthesis/`, `features/`, `models/`, the rest of
`decision/`, and all the Streamlit pages. Each stub names its owner and module.
Grep for `TODO(` to find them all.

### Deliberately absent

- No agent, no LLM client in any decision path, no vector store. That is the
  point of [ADR 0004](docs/adr/0004-llm-has-no-write-path.md).
- No network model and no NLP model. Removed in session 3 — those are other
  components' work. The dependency cost of that decision was ~4.5 GB of
  install (transformers, peft, CAMeL Tools, LangChain, Chroma,
  sentence-transformers), which matters on a machine with ~20 GB free.
- No syllabus-coverage tracking.

---

## 5. Environment state on this machine

| Thing | State |
|---|---|
| Git 2.55.0 | Installed at `D:\Git` — **not on the default PATH location** |
| GitHub CLI 2.101.0 | Installed at `D:\GITHUB_CLI` |
| Docker 29.8.0 | Installed under `%LOCALAPPDATA%\Programs\DockerDesktop` |
| conda 26.5.3 | Installed at `D:\Anaconda` |
| Python | base is **3.14.6** — wrong version; also 3.10 present |
| Node 26.8.2, VS Code 1.137.0 | Present, not needed for this branch |
| **conda `cvm` env** | **Not created yet** ← first thing to do |
| **git identity** | **Not configured** (`user.name`, `user.email` empty) |
| **`gh auth login`** | **Not done** |
| **Docker daemon** | **Not running** (Docker Desktop not started) |
| **`.env`** | **Not created** (copy from `.env.example`, generate a real salt) |
| Free disk | ~20 GB on C:, ~20 GB on D: — **tight**, see `data/README.md#disk-budget` |

---

## 6. What to do next

In order. Do not skip step 1.

0. **Answer the market questions** in
   [`docs/MARKET_QUESTIONS.md`](docs/MARKET_QUESTIONS.md) and fill in
   `conf/market.yaml`. The synthesis engine is blocked on this — everything
   after step 4 consumes it, so getting it wrong means regenerating the
   population and retraining.
1. **Set up the environment and prove the skeleton works** — follow
   [`docs/TESTING.md`](docs/TESTING.md) end to end. It is a numbered walkthrough
   with a checkpoint after every step. Budget one to two hours.
2. **Make the first commit.** Nothing is committed yet.
3. **Download the core datasets** (A, C first — they are small and unblock the
   baseline), then run the EDA: the UCI dedup audit (~300 duplicate rows) and
   the `Customer Value` leakage audit. These two findings are pitch material,
   so record the numbers.
4. **Build Layer 1 (`ingest/`)** — the schema contracts and the hashing. Every
   later layer depends on it, and the privacy commitment is enforced here.
5. **Build Layer 3 features + splits before any model.** Point-in-time
   correctness is the invariant that, if broken, silently invalidates every
   metric downstream. Un-`xfail` the tests in `tests/leakage/` as you go.
6. **M1 Arm A (LightGBM) + calibration** — the first real model, and the one
   everything else consumes.
7. Then, roughly in parallel: M2 (value/CLV), M4 (repayment PD, shares M1's
   pipeline), M3 (pricing — the guardrails are already written and tested).
8. **M1 Arm B (LSTM) on Colab.** The only GPU work left in this branch.

### Known gaps to close

- `tests/leakage/` and `tests/guardrails/test_advance_safety.py` have `xfail`
  markers on their behavioural tests. Each `xfail` is a deliberate marker of
  something not built. **Remove the marker as you implement**, so CI output
  tracks real progress.
- The `ORG/REPO` badge URLs in [`README.md`](README.md) and `@ali` in
  [`.github/CODEOWNERS`](.github/CODEOWNERS) are placeholders.
- `docs/model_cards/*.md` are stubs. They are also the RAG corpus published to
  the Copilot and Chatbot, so a stale card becomes a wrong answer in someone
  else's demo.
- `conf/market.yaml` is filled with **assumptions, not facts**. Every value
  marked `ASSUMPTION` needs replacing with real operator data or explicitly
  defending in the report.
- `D:\Sic\Proposal\` is an empty leftover folder. Harmless (git ignores empty
  directories); delete it if it bothers you.

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
- **Anything used to generate the synthetic label must be excluded from
  features.** `synthesis/hazard.py` exports `LABEL_GENERATING_FIELDS`, and a
  leakage test cross-checks it against `conf/features.yaml`. This is the
  subtlest failure mode in the whole project: a model that scores beautifully
  by reading its own label back out.
- **Colab cuts sessions without warning.** Checkpoint to Drive every epoch for
  the three GPU modules.

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

## 9. How to update this file

Append a dated entry to §8 at the end of every working session, and update §2
and §6 so they describe the *current* state rather than the history. Keep
entries factual: what changed, what was decided, what broke.

If you are an AI session picking this up: read this file, then
`docs/INTEGRATION.md` if the work touches the API, then the specific module's
docstring. Do not re-derive decisions already recorded in §3 — challenge them
explicitly if you disagree, but do not silently reverse them.
