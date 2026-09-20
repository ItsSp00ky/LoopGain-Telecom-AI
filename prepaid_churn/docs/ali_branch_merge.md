# Merging Ali's `Ali_Branch` into this module

This file records every step of combining Ali Marghem's work on `Ali_Branch` with this module.
The decision behind it is decision 15 in [decisions.md](decisions.md); decisions 16 and 17 follow from it.
Add a dated entry to the step log for every step, and keep the port table current.

## Source

- Branch: `origin/Ali_Branch`, commit `06890f6a5d8130b224cf1463f9a24892be23f0e2` (2026-09-19, 33 commits, 191 files).
- Fetched on its own with `git fetch origin Ali_Branch`; `main` was not fetched or merged.
- Author: Ali Marghem (`ali-margem <ali.m.margem@gmail.com>`).
- Read a file from it without checking it out: `git show 06890f6:<path>`.

## Rules for porting

- Port by hand, never with `git merge` (the branch has unrelated history and root-level files).
- Every port names its source path in the table below and in the commit message.
- Commits that port Ali's work credit him with `Co-authored-by: ali-margem <ali.m.margem@gmail.com>`.
- Ported code follows this module's rules (CLAUDE.md): pure functions, thin CLI, small hand-made test frames, real data only.
- Anything measured on Ali's generated population is not carried over as a result.

## Port table

| # | What | Source in `Ali_Branch` | Destination here | Ticket | Status |
|---|---|---|---|---|---|
| 1 | Almadar source files (packages, tariffs, service rules) | `Almadar/*` | `data/almadar/source/` | T16 | Done (byte-for-byte copies) |
| 2 | Almadar catalogue, recharge cards, tariffs, emergency credit rules | `conf/catalogue.yaml`, `conf/market.yaml`, `conf/advance.yaml` | `data/almadar/offers.csv`, `data/almadar/market.toml`, `src/prepaid_churn/almadar.py` | T16 | Done |
| 3 | Money onto Almadar's scale | `src/cvm/synthesis/quantile_map.py` | `src/prepaid_churn/almadar.py` | T18 | Done (the idea; a linear rate replaces the quantile map) |
| 4 | Serving lessons | `HANDOFF.md` section 7, `src/cvm/models/registry.py` | `src/prepaid_churn/bundle.py`, `src/prepaid_churn/scoring.py` | T8 | Done |
| 5 | Prepaid value segmentation | `src/cvm/features/rfm_le.py`, `src/cvm/models/m2_value/segmentation.py` | `src/prepaid_churn/value.py`, `src/prepaid_churn/segmentation.py` | T10 | Done (adapted design, training-frozen cutoffs) |
| 6 | Offer engine design and guardrails | `src/cvm/decision/*`, `conf/pricing.yaml` | T11 | T11 | Planned |
| 7 | API design, pseudonymous IDs, phone-number check | `src/cvm/api/*`, `src/cvm/ingest/hashing.py` | T15 | T15 | Planned |
| 8 | Integration contract and grounding rules for LLM consumers | `docs/INTEGRATION.md`, `docs/adr/0004-llm-has-no-write-path.md` | `docs/integration.md` | T20 | Planned |
| 9 | Screens (overview, subscriber view, campaign builder, SMS preview) | `apps/*` | T14 | T14 | Planned |
| 10 | Model card template | `docs/model_cards/TEMPLATE.md` | T9 | T9 | Planned |
| 11 | Two-model uplift, Qini, Criteo validation | `src/cvm/models/m3_uplift/*`, `src/cvm/ingest/criteo_uplift.py` | T17 | T17 | Planned |
| 12 | Emergency credit rules and affordability ceiling | `conf/advance.yaml`, `src/cvm/decision/advance_limit.py` | T19 | T19 | Planned |
| 13 | Synthesis engine and quality gate | `src/cvm/synthesis/ctgan_engine.py`, `quality_gate.py` | T13 | T13 | Planned |

Not ported, with the reason in decision 15: the generated population and `hazard.py` labels, the repayment model, survival models, DuckDB, MLflow, Docker, conda, the eight-model benchmark, and the Cell2Cell, IBM, UCI, Hillstrom and Online Retail loaders.

Useful for the team but outside this module: `docs/integration/copilot_starter/` in `Ali_Branch` is a starting point for the employee copilot, which Taha owns in the action plan.

## Step log

### Step 1 - Review (2026-09-19, Taha + Claude)

- Fetched `Ali_Branch` only and confirmed it contains no `main` commits and shares no history with `tahaDev`.
- Read Ali's `HANDOFF.md`, `docs/ROADMAP.md`, `docs/INTEGRATION.md`, the synthesis layer, the configs and the Almadar files.
- Main finding: the churn label is drawn from a hand-written logistic formula over six fields, on a population generated from Cell2Cell.
  Ali's own roadmap says logistic regression wins because the generator is linear, and that the results are not evidence of production performance.
- Real and valuable: the Almadar data, the offer engine design, the integration contract with its LLM grounding rules, and the serving lessons.
- Ali's tests (368, as his handoff reports) were not run here: they need Python 3.11 through conda, about 3 GB of packages, Cell2Cell files from his machine and his hashing salt.

### Step 2 - Re-plan (2026-09-19, Taha + Claude)

- Taha asked to take the best of both efforts into one module on `tahaDev`, built around Almadar, and to keep the team platform's integration as the real goal.
- Re-read the reviewed SIC action plan: the instructor asks for a narrow customer MVP, de-identification, access control, human approval, and a retrieval-only copilot.
- Wrote decisions 15, 16 and 17, rewrote the tickets from T8 onward, and added T18 (Almadar view), T19 (emergency credit) and T20 (integration check).
- Defaults taken where Taha did not choose, all open to change: Almadar only, the folder keeps its name `prepaid_churn/` until Ali agrees on a new one, and emergency credit stays as a small rule-based ticket.

### Step 3 - T16 Almadar catalogue and market facts (2026-09-19, Claude)

- Copied the four files of `Almadar/` into `data/almadar/source/`; their SHA-256 hashes match the `06890f6` blobs.
- Built `data/almadar/offers.csv` from the operator file: prices, stated volumes, minutes, speeds and member counts are parsed from it, and the IDs follow `conf/catalogue.yaml`.
  All 57 packages are in, including the five Mix families that Ali's catalogue dropped without a recorded reason (open question in TICKETS.md).
- Each volume records where it comes from (`stated`, `name`, `reported` or `none`); Ali's catalogue flagged inferred volumes once for the whole file, not per package.
- Moved the facts from `conf/market.yaml`, `conf/catalogue.yaml` and `conf/advance.yaml` that later tickets need into `data/almadar/market.toml`, each with a status and a source.
  The recharge cards became `reported` instead of `confirmed`, because no operator document for them is in the repo.
- Not carried over from `conf/market.yaml`: the recharge popularity split, channel shares, dual-SIM share, calendar and language shares, which only fed the generated population.
- `src/prepaid_churn/almadar.py` validates both files and checks the catalogue row by row against the operator file; `tests/test_almadar.py` covers each rule and each kind of mismatch.
- `docs/almadar.md` explains the files for the chatbot owners and for future refreshes.

### Step 4 - T8 model bundle and scoring (2026-09-19, Claude)

Ali's serving lessons (his `HANDOFF.md` section 7) were applied as design rules, not ported as code:
- "Any statistic a serving path needs must travel on the artefact": the bundle carries the features, thresholds and a sample row, and nothing is computed from the scored batch except the month end date the data contract requires.
- "Loading is not working": loading predicts the stored sample row and refuses a bundle whose answer changed.
- Library skew between the pickle and the installed versions: `manifest.json` records the versions and is checked before anything is unpickled (Ali pinned scikit-learn below 1.8 instead; we record and compare every version).
- "A batch of one row is its own worst case": a test scores each customer alone and compares it with the full batch.
  It found a real bug on the first run: pandas 3 typed an all-empty reason column differently in a one-row batch.
- The zero SHAP background: avoided by design, because LightGBM's own `pred_contrib` needs no background sample.

### Step 5 - T18 Almadar view of the real customers (2026-09-19, Taha + Claude)

- Taha chose Ali's 40 LYD ARPU as the anchor.
- Ali's `quantile_map.py` maps amounts onto the recharge cards through assumed card shares (54% on 5 LYD, and so on).
  We used one linear rate instead (40 LYD over the measured mean recharge), which keeps the real differences between customers and needs only the ARPU assumption.
  The result backs Ali's instinct: for 88.9% of active customers the nearest card to their usual top-up is 5 LYD.
- The bundle a customer holds, which Ali's cannibalisation guard needs (T11), comes from the real monthly and short pack purchases of the upGrad data.

### Step 6 - Handover to Ali (2026-09-19, Taha + Claude)

- Taha asked to push the combined work so Ali can continue it.
- Checked the handover path first: a fresh clone of `tahaDev`, `uv sync` and the six pipeline commands rebuilt everything in about a minute, with a byte-identical champion, the same bundle version (`lightgbm-2026-09-19-ef9430fb`), identical scores and Almadar view, no changed report, and all tests green.
- Wrote "For Ali: how to continue from here" at the top of the Handoff in `TICKETS.md`, with a first message for his Claude session, and brought `README.md` up to date.
- Suggested split, for Taha and Ali to confirm: Ali on T10 and T11, Taha on T15 and T20.

### Step 7 - T10 value tiers on Ali_Branch (2026-09-20)

- Read `src/cvm/features/rfm_le.py` and `src/cvm/models/m2_value/segmentation.py` from commit `06890f6`.
- Adapted the five prepaid dimensions, reverse recency scoring and the rules-versus-clusters comparison to the existing two-month upGrad windows.
- Replaced batch percentile ranks with saved training cutoffs so a subscriber's tier is stable when scored alone or in a different batch.
- Used the recorded recharge amounts, tenure and observed service breadth; did not port synthetic lifetime-spend, continuity or recharge-regularity proxies.
- Preserved tied values and neutral constant dimensions, and kept missing-value handling in the existing data contract.
- K-Means uses a bounded silhouette sample, Ward a 300-row sample, and PCA only a visualization role.
- No synthetic population result or natural-segment claim was carried over.
- The 12-month revenue formula and hazard sensitivities are explicit scenario assumptions (decision 19).
- Work is committed only to the authorized `Ali_Branch` delivery; decision 18 supersedes the original branch handoff.
