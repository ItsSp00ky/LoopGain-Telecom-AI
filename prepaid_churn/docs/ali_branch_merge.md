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

- Port by hand from Ali's original tree at `06890f6` and earlier, never with `git merge`: that history is unrelated to this branch and carries root-level files.
- This no longer applies to `Ali_Branch` after 2026-09-20.
  Ali adopted this tree as his baseline (decision 18), so his later commits are ordinary commits on this history and were taken by fast-forward (decision 24).
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
| 6 | Offer engine design and guardrails | `src/cvm/decision/*`, `conf/pricing.yaml` | `src/prepaid_churn/retention.py`, `src/prepaid_churn/campaign.py`, `data/almadar/retention.toml` | T11 | Done (adapted design, bonus proposals and named review) |
| 7 | API design, pseudonymous IDs, phone-number check | `src/cvm/api/*`, `src/cvm/ingest/hashing.py` | `src/prepaid_churn/api.py`, `src/prepaid_churn/service.py`, `src/prepaid_churn/privacy.py` | T15 | Done (adapted design, four read-only endpoints and per-consumer keys) |
| 8 | Integration contract and grounding rules for LLM consumers | `docs/INTEGRATION.md`, `docs/adr/0004-llm-has-no-write-path.md` | `docs/integration.md` | T20 | Done (adapted to this service's endpoints; his six grounding rules kept) |
| 9 | Screens (overview, subscriber view, campaign builder, SMS preview) | `apps/*` | `app/`, `src/prepaid_churn/demo.py` | T14 | Done (adapted design, four screens with named approval) |
| 10 | Model card template | `docs/model_cards/TEMPLATE.md` | `docs/model_card.md` | T9 | Done (adapted structure, filled from the committed reports) |
| 11 | Two-model uplift, Qini, Criteo validation | `src/cvm/models/m3_uplift/*`, `src/cvm/ingest/criteo_uplift.py` | T17 | T17 | Planned |
| 12 | Emergency credit rules and affordability ceiling | `conf/advance.yaml`, `src/cvm/decision/advance_limit.py` | `src/prepaid_churn/advance.py` | T19 | Done (ceiling and denominations only; no repayment model) |
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
  All 57 packages are in, including the five Mix families that Ali's catalogue dropped (his commit `62040af` of 2026-09-18 records the removal and its consequences, but not why they should go; open question in TICKETS.md).
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

### Step 8 - T11 retention proposals and review on Ali_Branch (2026-09-20)

- Read `conf/pricing.yaml`, `src/cvm/decision/guardrails.py`, `budget_lp.py` and `decision_log.py` at `06890f6`.
- Adapted catalogue-only actions, the held-bundle cannibalisation guard, value cap, budget allocation, equal-spend comparison and replayable decision snapshots.
- Followed the current T11 ticket's greedy allocation instead of adding an LP solver or infrastructure.
- Used declared saved-share assumptions with the frozen churn model and T10 revenue scenario, not Ali's generated uplift or CLV results.
- Kept catalogue prices unchanged and implemented bonuses, including the existing morning product with its stated hours.
- Added reproducible holdout assignment, Arabic/English reasons, named approve/reject events and approved-only release.
- Did not port demographic pricing, simulated peak-load evidence, hazard-derived ladders or claims about annual spending without a ledger.
- The real-export report records unavailable risk and zero proposals because this checkout has no gated real bundle; positive paths are exercised only by hand-made tests.
- Decision 20 records the assumptions and limitations; T15 still owns authenticated shared access.

### Step 9 - T15 integration service on Ali_Branch (2026-09-21)

- Read `src/cvm/api/main.py`, `deps.py`, `schemas.py`, the health, cohort, offer and subscriber routers, and `src/cvm/ingest/hashing.py` at `06890f6`.
- Ported the MSISDN pattern and the salted SHA-256 hash into `src/prepaid_churn/privacy.py`, keeping Ali's three corrections and the reasons he recorded for each.
  His version hashed whole frames and read the salt from a settings object; this one takes the salt as an argument and keeps only the two functions T15 needs.
- Adapted the shape of his API: response models as the integration contract, `/health` reporting each artefact separately, and the read-only cohort idea behind `/portfolio/summary`.
- Took his cohort lesson that revenue at risk is value weighted by churn probability, not the value of everyone who matched.
- Took his serving lesson, already applied in T8, that an artefact which deserialises is not an artefact that predicts, and reported loaded and usable separately.
- Did not port the feature store, DuckDB, the online/offline store split, the per-request feature read, CORS, the request-id middleware, the latency budget or the `/score`, `/offer`, `/advance` and `/cohort/query` endpoints.
  Those either belong to models this module does not have, or would give the service a way to compute a decision, which T15 explicitly forbids.
- Added what `Ali_Branch` did not have: per-consumer API keys enforced per endpoint, a refusal to start without them, the phone-number check on the request path, and an approved-only offer lookup.
- Ali's API had no authentication and allowed every CORS origin outside production; that part was not carried over.
- Decision 21 records the new dependencies, the access-control boundary and the reporting rules.

### Step 10 - T14 demo app on Ali_Branch (2026-09-21)

- Read `apps/_shared.py`, `apps/command_center/Home.py` and the Executive Overview, Subscriber 360 and Campaign Builder pages at `06890f6`.
- Ported the SMS part calculation, with Ali's GSM-7 against UCS-2 finding and his reason for it: one Arabic character forces the whole message into UCS-2, where a part is 70 characters and not 160.
- Ported the missing-output banner idea, which names what is absent and the command that produces it, and the right-to-left wrapper for Arabic.
- Took his Executive Overview rule that expected churners is the sum of calibrated probabilities rather than a count above a threshold.
- Took his Campaign Builder rule that a guardrail breakdown must state who was excluded and why, and his warning that the blanket comparison has to be made before the guardrails run.
- Took his Subscriber 360 lesson about keeping a one-row frame rather than a Series, and his rule that the lookup field refuses a raw number in the UI and not only in the backend.
- Did not port the RFM radar, the SHAP waterfall, the survival curve, the uplift quadrant, the leakage panel, the advance limit screen, the targeting CSV export, plotly or the `channel_sim` app.
  Those belong to models this module does not have, or to T17 and T19.
- Added what `Ali_Branch` did not have: the named approve and reject step from decision 14, writing through `campaign.review_file`, and a budget control that is an explicit preview which cannot be approved.
- Ali's app carried a synthetic-data caveat on every screen; the equivalent here is the no-bundle banner, because this module's numbers are real but its risk figures are unavailable without a gated bundle.
- Decision 22 records the Streamlit dependency, the preview boundary, the reporting rules and the five defects the browser check found.

### Step 11 - T9 documentation and model card on Ali_Branch (2026-09-21)

- Read `docs/model_cards/TEMPLATE.md` at `06890f6` and kept its structure: intended use, out-of-scope use, training data, metrics with the primary one first, calibration, explainability, limitations, ethical considerations, selection bias and maintenance.
- Kept his rule that accuracy is not a headline metric at a low base rate, and reported PR-AUC first with accuracy omitted entirely.
- Kept his insistence on an out-of-scope section, and on stating plainly that a model feeding a priced decision produces an input to a constrained decision rather than the decision.
- Adapted his "naive versus honest" section.
  No naive variant was run here, so instead of inventing one the card shows the validation PR-AUC of 0.4582 against the test 0.3477 and names the four traps the design avoids.
- Dropped the fields that describe infrastructure this module does not have: MLflow run, `conf/models/*.yaml`, the Evidently drift report and the temporal cut dates, which do not apply to a customer split.
- Replaced his mandatory generated-data caveat with the equivalent that is true here: the data is real but from another market, undocumented in provenance, four months long and licensed for education only.
- Every figure in the card is copied from a committed report and names it, because the employee copilot indexes the document (decision 17).
- `tests/test_model_card.py` compares the card's figures against those reports, so a stale number fails the suite rather than reaching the copilot.

### Step 12 - T19 emergency credit advice on Ali_Branch (2026-09-21)

- Read `conf/advance.yaml` and `src/cvm/decision/advance_limit.py` at `06890f6`.
- Ported the affordability ceiling, its 0.6 fraction and his reason for keeping it below 1, and the refusal to accept a fraction at or above 1.
- Ported the rule that only denominations the operator actually sells may be advised, so a ceiling of 2.9 LYD advises 1 LYD rather than inventing a 2 LYD advance.
- Ported the zero-residual finding, his honesty note that an equality is weaker evidence than an impossibility, and his correction that Libyana's Credit Loan does not describe Almadar.
- Computed the finding from `market.toml` instead of hardcoding it, and added a test showing it would retire itself if the smallest card ever changed.
- Adapted the basis: he asks for the modal top-up, and this data has only monthly totals and counts, so the quieter month's average per recharge is used and the report carries a sensitivity table for that choice.
- Did not port the PD model, the tier ceiling, the CLV cap, the cooling-off period, the chronic-distress screen, the lockout-risk step-down, reject inference or the fee structure.
  Each needs a repayment model, an advance history or balance-level fields that do not exist here, and decision 15 rules a repayment model out until an operator supplies one.
- Did not carry over any number he measured on his generated population.
- Decision 23 records the rule, the adaptation, the sensitivity and what was deliberately left out.

### Step 13 - Taking Ali's branch into `tahaDev` (2026-09-21, Taha + Claude)

- Fetched `Ali_Branch` only; `main` was not fetched.
  It had moved from `06890f6` to `ae38840`, thirteen commits, 65 files and about 9,000 added lines.
- Read every commit before touching anything: the baseline swap, the T21 review, T10, T11, T15, T14, T9 and T19.
- Confirmed the branches can be joined honestly: `22aefc8`, Ali's baseline, has exactly the tree of `bfb28ab`, and `bfb28ab` is an ancestor of `ae38840`.
- Verified his delivery here before taking it: 379 tests, lint and format green, and a full rebuild that reproduced bundle `lightgbm-2026-09-19-ef9430fb` and tier artifact `tiers-v1-cd15525cb3ef` with no committed report changed.
- Fast-forwarded `tahaDev` to `ae38840`; decision 24 records why this replaces hand-porting for his later work.
- Checked what his review changed in our files: identifiers read as text, stricter export and bundle checks, one calibration prediction reused instead of three, and the Almadar market values validated.
  None of it moves a model, a feature or a threshold, which the byte-identical rebuild confirms.
- Noted for Taha: the fast-forward also brings Ali's fixes to Ahmed's `antenna_cell_placement/` and the root `CODE_REVIEW.md`.

### Step 14 - T20 integration guide, example client and check (2026-09-21, Taha + Claude)

- Read `docs/INTEGRATION.md` at `06890f6` and kept its shape: why a service and not an import, health before the first call, the endpoint table, two rules for every call, a worked example per consumer, the grounding rules, what the copilot may index, and what this module needs from network ML.
- Kept all six of Ali's grounding rules almost unchanged, because they were the strongest thing in his document and they answer the instructor's question about why no language model decides anything.
- Rewrote every example against the endpoints this module actually serves, with real responses captured from a running service rather than invented ones.
- Adapted his network ML field contract: his was keyed by `cell_id` for a model that had cell features, and ours is keyed by the pseudonymous subscriber ID, because this module never sees a cell and the subscriber-to-cell mapping is the operator's.
  Stated plainly that adding any such field means a new frozen champion, so it is a version 2 change.
- Added what his document did not have: which files a retriever may index and which it may never touch, and a command that checks the seam instead of a document that describes it.
- Did not port `docs/integration/copilot_starter/`: it is scaffolding for the copilot itself, which is a different component and Taha's in the action plan.
- Decision 25 records why the example client is copied rather than imported and uses no dependency.

### Step 15 - The T20 walkthrough and what it changed (2026-09-21, Taha + Claude)

- Walked the questions each consumer really gets, instead of only checking that the documented calls answer.
- One gap mattered: an employee copilot could quote portfolio totals but could not answer "what do we know about the customer I have on the phone", because no endpoint served one subscriber to the copilot.
  `GET /subscribers/{id}/risk` closes it (decision 26); `Ali_Branch`'s API had the equivalent in its `/v1/subscriber/{id}` view, so this is closer to his design than the four endpoints were.
- The other gaps are recorded in the guide with the reason each one is not served, rather than left for a consumer to discover: the package a customer holds, the emergency credit advice, a bulk list of risky customers, and the review queue.
