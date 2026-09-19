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
| 1 | Almadar source files (packages, tariffs, service rules) | `Almadar/*` | `data/almadar/source/` | T16 | Planned |
| 2 | Almadar catalogue, recharge cards, tariffs, emergency credit rules | `conf/catalogue.yaml`, `conf/market.yaml`, `conf/advance.yaml` | `data/almadar/offers.csv`, `data/almadar/market.yaml` | T16 | Planned |
| 3 | Money onto Almadar's scale | `src/cvm/synthesis/quantile_map.py` | `src/prepaid_churn/almadar.py` | T18 | Planned |
| 4 | Serving lessons | `HANDOFF.md` section 7, `src/cvm/models/registry.py` | T8 bundle and scoring | T8 | Planned |
| 5 | Prepaid value segmentation | `src/cvm/features/rfm_le.py`, `src/cvm/models/m2_value/segmentation.py` | T10 | T10 | Planned |
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
