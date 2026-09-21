# Tickets

Work plan for the prepaid churn module.
Pick a ticket by writing your name in its **Owner** field.
A ticket is done only when its acceptance criteria pass and `ruff check`, `ruff format --check` and `pytest` are green.
The reasons behind every decision are in [docs/decisions.md](docs/decisions.md).

## Handoff

Update this section at the end of every working session.

**Last updated:** 2026-09-21 by Taha + Claude (Ali's branch taken into `tahaDev`, T20 delivered).

**Where the module is now**

- **One branch.** Ali built his delivery on top of `tahaDev` `bfb28ab`, so `tahaDev` was fast-forwarded to `Ali_Branch` `ae38840` instead of porting 9,000 lines by hand (decision 24).
  Both of us work on `tahaDev` from here; `Ali_Branch` stays as the record and is not worked on.
- **Ali's delivery was checked here before it was taken**: 379 tests, lint and formatting green, and a full rebuild that reproduced bundle `lightgbm-2026-09-19-ef9430fb` and tier artifact `tiers-v1-cd15525cb3ef` with no committed report changed.
  His review of our files (identifiers read as text, stricter export and bundle checks, one calibration prediction instead of three) moves no model, feature or threshold, which that rebuild proves.
- **The MVP is complete end to end**: T16, T8, T18, T10, T11, T15, T14, T9, T19 and now T20.
- **T20 is delivered except for the part that needs people.**
  [docs/integration.md](docs/integration.md) is the guide for the chatbot, copilot, network ML and antenna owners; `src/prepaid_churn/client.py` is the example client they copy; `churn check-integration` runs it against a live service and checks the four refusals.
  Its acceptance needs those owners to say the responses give them what they need, so the ticket stays open until they do.
- **Validation of T20 here**: 388 prepaid tests, lint and formatting pass; 9 of those tests are new, and no dependency was added.
  The check was run against a real service on 2026-09-21 holding the 30,000-subscriber base, a campaign with two approved offers and one rejected: status ok, 57 packages, the approved offer returned, 176,494 LYD at risk, and all four refusals correct.
- **What is left:** the owners' confirmation for T20, then T12 and T13, which cover the two graded syllabus chapters still missing (decision 8), and T17 last.

**For Ali: what changed on our side**

1. Your branch is now our branch.
   Taha reviewed your thirteen commits, checked them on his machine, and fast-forwarded `tahaDev` to `ae38840`; decision 24 says why that replaces the hand-porting rule of decision 15.
   Work on `tahaDev` from now on: `git pull --rebase` before you start, claim a ticket by writing your name in its Owner field, push when it is done.
   Nothing of yours was dropped, rewritten or renamed.
2. We took T20, the last MVP item, because the action plan gives Taha the chatbot, the copilot and the integration.
   New files: `docs/integration.md`, `src/prepaid_churn/client.py`, `tests/test_client.py`, and the `churn check-integration` command.
   Your `docs/INTEGRATION.md` at `06890f6` is where the shape came from, and your six grounding rules are kept nearly word for word; step 14 of [docs/ali_branch_merge.md](docs/ali_branch_merge.md) lists what was adapted and what was not.
3. Two things we found while using your work, neither of them a bug in it:
   - `churn decide` overwrites the committed `reports/decisions.md`, so running the documented command dirties a tracked file that records your readiness run.
     We restored it with `git checkout` rather than committing the new one.
     Worth a `--report` flag or a campaign-local path.
   - `test_api.py` and `test_demo.py` each build their own copy of the same four subscribers, and `tests/test_client.py` now makes three.
     If you touch those fixtures, moving them into `conftest.py` would be a good small cleanup; we left them alone rather than editing your tests.
4. Please still answer the open questions below that name you; the Mix packages and the source links for the Almadar files are the two that block nothing but weaken the report.
5. Your Claude can start from this, in the repo:

   > I am Ali. Taha took my `Ali_Branch` work into `tahaDev` and added T20. Read `prepaid_churn/CLAUDE.md`, the Handoff at the top of `prepaid_churn/TICKETS.md`, decisions 24 and 25 in `prepaid_churn/docs/decisions.md`, and steps 13 and 14 of `prepaid_churn/docs/ali_branch_merge.md`. Then rebuild the artifacts with the commands in the README, confirm the bundle is `lightgbm-2026-09-19-ef9430fb`, and tell me which ticket is next and what Taha still needs from me, before writing any code.

**Ali's delivery log (2026-09-20 and 2026-09-21)**

- Delivered on `Ali_Branch` under decision 18; that delivery is finished and decision 24 supersedes its branch instruction.
- T21 fixes export validation, identifier preservation, bundle consistency and repeated inference.
- T21 validation: 170 prepaid tests and 21 geospatial tests passed.
- T10 adds frozen value tiers, an explicit 12-month revenue scenario, and a training-only clustering comparison.
- T10 validation: 202 prepaid tests, lint, formatting and the locked offline environment check pass.
- Fitted tiers on 45,858 active training customers; assigned one tier to each of 30,000 unlabeled customers.
- The clustering result is weak (best silhouette 0.2766 at k=2); five value tiers remain a reporting convention.
- Run `uv run churn fit-tiers`, then `uv run churn tiers --tiers-only` without a churn bundle, or `uv run churn tiers` with the existing gated bundle.
- This checkout has no real churn bundle: the 30,000-row run contains tiers and explicitly unavailable risk-based values; the full bundle-to-scenario path is covered by hand-made integration tests.
- Both raw exports pass validation, and their model features are unchanged in both windows.
- The frozen model and the spent test window are unchanged.
- Rebuild old bundles with `uv run churn bundle` using the existing champion and gate, because the input contract fingerprint and bundle integrity checks changed.
- Findings and remaining work are in [../CODE_REVIEW.md](../CODE_REVIEW.md).
- T11 is implemented: catalogue bonuses, spend and cannibalisation guards, deterministic holdout, equal-spend comparisons and named approve/reject commands.
- T11 validation: 247 prepaid tests, lint and formatting pass; the 30,000-row readiness run creates no offers without a gated churn bundle.
- The readiness report records 27,582 active rows with unavailable risk, 2,418 silent rows and 2,965 holdout assignments; all proposals and releases remain empty.
- Positive recommendations, partial/all reviews, rejected-row exclusion, review locking and interrupted-write recovery are covered by hand-made tests.
- Run `churn decide` with the existing gated bundle for risk-based proposals, or `churn decide --tiers-only` for readiness; choose a new campaign output directory on each run.
- T15 is implemented: a read-only FastAPI service with four endpoints, one API key per consumer and a phone-number check on subscriber IDs.
- T15 validation: 299 prepaid tests, lint and formatting pass; 52 of those tests are new.
- `fastapi`, `uvicorn` and `httpx` are the first dependencies added since the module was built; decision 21 records why.
- Start it with `uv run churn serve` after setting `PREPAID_CHURN_CHATBOT_KEY` and `PREPAID_CHURN_COPILOT_KEY`; neither has a default and the service refuses to start without both.
- The OpenAPI page at `/docs` is generated from the response models, so it is the integration documentation for the chatbot and copilot owners.
- Run against this checkout on 2026-09-21: `/health` reports degraded with no bundle, `/catalogue` serves all 57 packages, `/portfolio/summary` summarises 30,000 subscribers with `risk_available` false, and no offer is released because none was approved.
- Outputs are read once at startup, so restart the service after a new `churn approve` release; `/health` shows which campaign is being served.
- T14 is implemented: four Streamlit screens over the released outputs, with the named approval step on the campaign screen.
- T14 validation: 325 prepaid tests, lint and formatting pass; 26 of those tests are new.
- Start it with `uv run streamlit run app/Home.py`; set `PREPAID_CHURN_CAMPAIGN_DIR` and `PREPAID_CHURN_PORTFOLIO` to show a campaign other than the first.
- `streamlit` is the fourth dependency added on this delivery; decision 22 records why, and charts use the Altair that Streamlit already installs.
- Every screen was opened in a browser against the 30,000-row export, a five-customer campaign and a one-customer campaign; that found five defects the unit tests had missed, all fixed.
- Approving on screen writes through the same locked, audited path as `churn approve`, and only approved rows reach `released.csv`.
- **For T11 to consider:** the approved Arabic message is 102 characters, so it sends and bills as two SMS parts; one part is 70 characters once any Arabic is present.
- T10, T11, T14 and T15 are complete; the next product work is T20 integration checks, which needs Taha and the chatbot and copilot owners rather than code alone.
- T9 is done: [docs/model_card.md](docs/model_card.md) covers intended and out-of-scope use, the data, the frozen metrics and thresholds, calibration, explanations, the approval step, the Almadar assumptions, limitations, ethics, selection bias and maintenance.
- T9 validation: 341 prepaid tests, lint and formatting pass; 16 of those tests compare the card's figures against the reports they cite.
- **The fresh-clone check was rerun on 2026-09-21 and passed:** the README pipeline rebuilt bundle `lightgbm-2026-09-19-ef9430fb` and tier artifact `tiers-v1-cd15525cb3ef`, and `git status` showed no changed report.
- That confirms T21, T15, T14 and the four new dependencies did not move the frozen champion or any committed number.
- With a real bundle the 30,000 unlabeled customers score high 1,209, medium 3,594, low 22,779 and already silent 2,418.
- T19 is done, the first experiment after the MVP: `churn advance` advises an emergency credit limit from recharge behaviour alone.
- T19 validation: 379 prepaid tests, lint and formatting pass; 38 of those tests are new, and no dependency was added.
- **The T19 result is a finding about the product, not about the rule.** This base tops up often in very small amounts, median typical top-up 1.89 LYD.
- So 46.1% of customers cannot carry even the 1 LYD advance and still have balance left, and the flat 5 LYD data advance suits only 4.65%, though the operator offers it to anyone with a low balance.
- The zero-residual finding is computed, not asserted: the smallest card, the data advance and the top airtime rung are all 5 LYD.
- The "typical top-up" basis is an assumption that moves the headline by twenty points, so `reports/emergency_credit.md` carries a sensitivity table instead of hiding it.
- T9, T10, T11, T14, T15 and T19 are complete.
- T20 is the last MVP item and needs Taha and the chatbot and copilot owners rather than code alone.
- **T12 and T13 are graded:** decision 8 says SIC grades syllabus coverage, and Ch 8, Ch 9 RNN (T12) and Ch 9 GAN (T13) are the two chapters still uncovered. T17 covers no chapter.

The rebuild commands and the fresh-clone check that used to sit here are in [README.md](README.md); the branch instructions above replace the 2026-09-19 ones.

**Status**
- T0 to T7 are done: the churn model is trained, calibrated and evaluated once on the test month (`reports/evaluation_all.md`).
  LightGBM test ROC-AUC 0.891, PR-AUC 0.348; the riskiest 10% of customers hold 61.5% of next month's churners.
- The data is committed in `data/raw/` (`train.csv`, `test.csv`, `data_dictionary.csv`), so a fresh clone can run everything (decision 9).
- `reports/profile.md` holds the real-data profile; the T1 Findings below summarise it.
- `docs/data_contract.md` is the input contract (generated by `uv run churn contract`); the real `train.csv` and `test.csv` both pass `uv run churn validate`.
- Integration with the team's chatbot and copilot is designed in decisions 10 and 17; the tickets T8, T11, T15, T16 and T20 follow it.
- The instructor reviewed the SIC action plan on 2026-09-19: success thresholds (decision 13) and a human approval step for retention actions (decision 14) are now part of the plan (T7 result, T8, T9, T11, T14, T15).
  The current champion passes all four thresholds.
- Ali's parallel work on `Ali_Branch` was reviewed and is being combined into this module (decisions 15, 16 and 17).
  Every step is logged in [docs/ali_branch_merge.md](docs/ali_branch_merge.md).
- Almadar Aljadid is now the operator (decision 16), and the customer MVP comes first, built to plug into the team platform (decision 17).
- T16 is done: `data/almadar/` holds all 57 Almadar packages and the market facts, each with a status (`docs/almadar.md`).
- T8 is done: `churn score` writes the subscriber output contract (`docs/output_contract.md`) from the gated bundle `lightgbm-2026-09-19-ef9430fb`; it is the integration point for the chatbot, the copilot and T11.
- T18 is done: `churn almadar-view` shows every customer in LYD and Almadar packages, at the 40 LYD ARPU Taha chose (`reports/almadar_view.md`).
- A fresh clone rebuilds everything and reproduces the champion byte for byte, checked on 2026-09-19, again on 2026-09-21 by Ali, and again on 2026-09-21 here after his branch was taken in.
- T20 is done apart from its acceptance: the guide, the example client and `churn check-integration` exist and were run against a live service; the chatbot and copilot owners have not confirmed yet.
- `tahaDev` now also carries Ali's fixes to Ahmed's `antenna_cell_placement/` and the root `CODE_REVIEW.md`; they are Ali's work, and the team has to see them before anything reaches `main`.

**Blocked on**
- T20's acceptance: the chatbot and copilot owners have to read [docs/integration.md](docs/integration.md), call the service with `churn check-integration`, and say in the T20 Findings whether the responses give them what they need.
  Nothing else waits on it; the code is written and tested.

**Next steps, in order (the MVP path from decision 17)**
1. T16 Almadar catalogue and market facts (done).
2. T8 model bundle, batch scoring and the output contract (done).
3. T18 Almadar view of the real customers (done).
4. T10 value tiers and T11 offers with human approval (done).
5. T15 integration service (done, Ali), then T20 integration check (done here, Taha + Claude, apart from the owners' confirmation).
   The suggested split had Taha taking T15 and T20; Ali took T15 on 2026-09-21 because T11 was finished and the endpoints were the next thing blocking the platform.
6. T14 demo app (done, Ali) and T9 documentation with the model card (done, Ali).
7. The MVP now works end to end: T19 (done, Ali), then T12 and T13, which cover the two graded syllabus chapters still missing (decision 8), and T17 last.
   T12 and T13 are the next work worth doing, and they are graded; whoever picks one writes their name in its Owner field first.
   The test window is spent: T12 compares against the frozen T7 numbers and must not change any T7 choice.

**Open questions**
- **Ali's agreement:** answered in practice on 2026-09-20, when Ali adopted this tree as his baseline and built on it (decision 18).
  He should still say whether he disagrees with anything decisions 15 to 17 took or left out, and now also with decisions 24 and 25.
- **Folder name:** the module now covers more than churn; rename `prepaid_churn/` (for example to `cvm/`, like Ali's package) once Ali agrees.
- **Almadar sources:** Ali's Almadar files have no source links; ask him where each came from (website page, app screenshot or shop) so T16 rows can cite them.
- **Mix packages:** Ali removed the five Mix families (20 data-and-voice packages) in commit `62040af` of 2026-09-18.
  That commit shows the removal was deliberate and handled, but not why; ask whether the operator still sells them (`docs/almadar.md`).
- **Almadar ARPU:** Taha chose 40 LYD per month for T18 on 2026-09-19; it is still an assumption, so replace it if an operator figure appears (one number in `data/almadar/market.toml`).
- **`churn decide` overwrites a committed report:** it rewrites `reports/decisions.md`, so running the documented command leaves a tracked file dirty.
  Ali's call: a `--report` path, or write it beside the campaign.
- **The two graded experiments:** T12 (sequence benchmark) and T13 (synthetic data) are the last syllabus chapters uncovered, and nobody owns either.
  Taha and Ali should split them.
- **Action plan dataset:** the team's SIC action plan lists `telco_customer_churn` (the IBM data) for churn.
  We use the upGrad prepaid data instead (decisions 1 and 5), because the IBM data is fictional and postpaid.
  Taha should tell the team leader so the action plan matches the work.

## Decisions already made

These are settled and every ticket must respect them.
Reasons are in [docs/decisions.md](docs/decisions.md).

- **Dataset:** upGrad "Telecom Churn Case Study" prepaid data, Kaggle `train.csv` (69,999 customers, months 6, 7, 8 plus a month 9 churn label in `churn_probability`).
  Kaggle's `test.csv` has no labels and is not used for evaluation.
- **Churn definition:** usage-based.
  A customer churns in month `m` when incoming calls, outgoing calls, 2G data and 3G data are all zero in month `m`.
  The rule lives in `src/prepaid_churn/labels.py`.
- **Two windows with relative month names.**
  Features always come from "previous month" and "current month", and the label from "next month".
  - Window A: features from months 6 and 7, label = churn in month 8, computed by us.
  - Window B: features from months 7 and 8, label = Kaggle's month 9 label.
- **Customer split:** customers are split 70/15/15 into train, validation and test, stratified by the window A label.
  - Train customers: fit models on window A.
  - Validation customers: early stopping, calibration and threshold choice on window A.
  - Test customers: final evaluation on window B, run once after everything is frozen.
- **No leakage:** a feature may only use months up to and including "current month".
  Month 9 information never enters features.
- **Eligibility:** only customers active in the current month are trained on, validated and scored (decision 12).
- **High-value filter:** optional flag, off by default.
  When on, it keeps customers whose average recharge amount over the two feature months is at or above the 70th percentile (the top 30%).
- **Models:** logistic regression baseline and LightGBM, with probability calibration.
  PCA is never a model input, because it destroys per-customer explanations.
  PCA is allowed only for the T10 segment plot.
- **Success thresholds** (decision 13), measured on an out-of-time test (a later month, unseen customers, active customers only).
  A model is fit for use only if it passes all four:
  1. Capture: the riskiest 10% of customers contain at least 50% of the churners.
  2. Better than chance: PR-AUC is at least 3 times the churn rate.
  3. Better than the baseline: the champion's PR-AUC is higher than logistic regression's on the same test.
  4. Calibration: the mean predicted churn rate is within 1 percentage point of the observed rate.
- **Human approval** (decision 14): the system only proposes retention offers.
  A named person approves or rejects them before any offer is sent or shown by the chatbot, and every approval is logged.
- **Operator** (decision 16): Almadar Aljadid.
  The churn model trains on real upGrad customers in their original units; the business layer shows them in Almadar terms (T18).
- **MVP first** (decision 17): one customer use case, integrated with the chatbot and copilot, before any extra experiment.
  No LLM in any path that sets an offer, price or credit limit; pseudonymous IDs; separate API keys for the chatbot and the copilot.
- **Ali's work** (decision 15): ported by hand from `Ali_Branch`, never merged with git, and every port logged in `docs/ali_branch_merge.md`.
- **Syllabus experiments** (T12, T13) use a separate `experiments` dependency group, so the core package stays small.
- **Data in git:** the raw Kaggle files in `data/raw/` are committed (decision 9).
  `data/processed/` and `artifacts/` are git-ignored and rebuilt by the pipeline.
  Reports with aggregate numbers (`reports/`) are committed.

## Conventions

- Code lives in `src/prepaid_churn/`, tests in `tests/`.
- Every pipeline stage is a set of pure functions that can be tested without files, plus a thin CLI subcommand in `cli.py`.
- Unit tests use small hand-made DataFrames (see `tests/conftest.py`), never the real dataset.
- Run everything through `uv run`.

## T0 - Scaffold

**Owner:** Claude
**Status:** Done
**Depends on:** nothing

Scope:
- `uv` project with pinned lockfile, ruff and pytest.
- Git-ignored `data/processed/` and `artifacts/` folders.
- Empty `churn` CLI.

Acceptance:
- `uv run churn --help` works.
- Lint, format check and tests pass.

## T1 - Data profiling

**Owner:** Claude
**Status:** Done
**Depends on:** T0

Scope:
- Group the columns by month: `split_month` and `monthly_columns` in `data.py` (handles `_6` suffixes and `jun_vbc_3g`-style prefixes).
- Missing-value share per column and month, and whether columns go missing together (minute columns with `onnet_mou`, data recharge columns with `date_of_last_rech_data`).
- Whether total minutes are zero when minute columns are missing, which tests the "missing means zero" hypothesis.
- Constant columns, duplicate IDs and rows, negative values.
- Usage-based inactivity (the label rule) and recharge-based inactivity (no recharge at all) per month, and how much they overlap.
- Kaggle's month 9 label rate, how many month 9 churners were already inactive in month 8, and the label rate for active vs inactive customers in month 8.
- `churn profile` command that writes `reports/profile.md`.

Acceptance:
- `reports/profile.md` exists, built from the real `train.csv`.
- The "Findings" subsection below states, with numbers, what the report confirms or changes for T2, T3 and T4.

Findings (from `reports/profile.md`, 69,999 customers, 172 columns):
- Missing values come in exactly two blocks, and both mean "nothing happened", so they become 0:
  - Voice block: 29 minute columns always go missing together (agreement 1.0 with `onnet_mou`), for 3.9%, 3.8% and 5.3% of customers in months 6, 7 and 8.
    For 100% of those customers, total incoming and outgoing minutes are 0.
  - Data block: 10 data recharge columns always go missing together with `date_of_last_rech_data` (agreement 1.0), for 74.9%, 74.5% and 73.7% of customers: no data recharge that month.
    `fb_user` and `night_pck_user` are 0/1 flags in this block, so missing means 0.
- `date_of_last_rech` is missing exactly when `total_rech_num` is 0 (100% agreement; 1,101, 1,234 and 2,461 customers).
  So missing means "no recharge this month", which T3 must encode as its own recency value, not as 0.
- 13 columns carry no information (one value, sometimes plus missing values): `circle_id`, `loc_og_t2o_mou`, `std_og_t2o_mou`, `loc_ic_t2o_mou`, `last_date_of_month_6/7/8`, `std_og_t2c_mou_6/7/8`, `std_ic_t2o_mou_6/7/8`.
  The month end dates are fixed (2014-06-30, 2014-07-31, 2014-08-31).
- No duplicate IDs and no duplicate rows.
- Negative ARPU: 292, 341 and 352 customers in months 6, 7 and 8 (minimum -2,258.7); small negatives in `arpu_2g` and `arpu_3g`.
  75% of the customers with negative `arpu_8` made no recharge in month 8, so these look like billing adjustments, not errors.
- Label: 10.19% of customers churn in month 9 (7,132 of 69,999).
- Usage-based inactivity is 6.8%, 6.4% and 7.8% in months 6, 7 and 8; recharge-based inactivity is only 1.6%, 1.8% and 3.5%.
  Most usage-inactive customers still recharged (5.8% of all customers in month 8), so the two definitions disagree.
  We keep the usage-based definition, because Kaggle's month 9 label uses it.
- 59.9% of month 9 churners were already usage-inactive in month 8.
  Customers inactive in month 8 churn at 77.9%; customers active in month 8 churn at 4.4%.
  This drives the eligibility question in the Handoff section.

## T2 - Input data contract

**Owner:** Claude
**Status:** Done
**Depends on:** T1

Scope:
- The contract is written once as column groups in `src/prepaid_churn/schema.py` (`GROUPS`).
  The pandera schema, the T3 cleaning rules and `docs/data_contract.md` are all built from it, so they cannot drift apart.
- Column checks: types, non-negative amounts, 0/1 flags, dates inside their month, unique IDs.
- Row rules from the T1 Findings: the voice block and the data block are complete or entirely missing, the recharge date is missing exactly when there was no recharge, and every month has a month-end date.
- The 13 no-information columns are not part of the contract; extra columns are allowed and ignored.
- `validate` collects every problem and raises one readable error; `churn validate` checks a file, `churn contract` regenerates the document.
- Dates are accepted as month/day/year (Kaggle) or year-month-day (ISO), so an operator export can use either.

Acceptance:
- The real `train.csv` and `test.csv` pass `uv run churn validate`.
- Tests show that missing columns, wrong types, out-of-range values and broken row rules fail with clear errors, all reported at once.
- A test fails when `docs/data_contract.md` is out of date.

## T3 - Cleaning

**Owner:** Claude
**Status:** Done
**Depends on:** T2

Scope (rules confirmed by the T1 Findings), in `src/prepaid_churn/clean.py`:
- Keep only contract columns, which drops the 13 no-information columns and any extra operator columns.
- Voice block and data block missing values become 0.
- `no_voice_record_<month>` flag: 1 when the whole voice block of the month was missing.
- `date_of_last_rech` and `date_of_last_rech_data` become `days_since_last_rech_<month>` and `days_since_last_rech_data_<month>`: days from the date to the month end.
  No recharge in the month gets the number of days in the month (for example 31 for August), one more than any real value, so larger always means staler.
  Recency across months (for example "no recharge this month, last one 12 days before it") is a T5 feature.
- Negative ARPU values stay as they are (billing adjustments).
- `id` stays in the cleaned data as the key; T4 keeps it out of the features.

Acceptance:
- One unit test per rule on the hand-made frame in `tests/conftest.py`.
- Cleaning twice gives the same result as cleaning once.

Result on the real data: 69,999 rows, 172 columns in, 162 columns out, no missing values left.

## T4 - Windows, labels and split

**Owner:** Claude
**Status:** Done
**Depends on:** T3

Scope, in `src/prepaid_churn/windows.py`:
- `window_features`: every monthly column becomes `prev_<base>` and `cur_<base>`, plus `tenure_days` from `aon`.
  `aon` is a snapshot from data extraction; the one-month difference between windows is small against its 180 to 4,337 day range.
- `window_label`: window A uses our usage rule on month 8; window B uses Kaggle's month 9 label.
- Eligibility: only customers active in the current month (decision 12).
- Optional high-value filter: average airtime plus data recharge amount over the two window months in the top 30%, computed among eligible customers of that window.
- Customer split 70/15/15, stratified by the window A label, seed 42.
- `churn build-dataset [--high-value]` writes `train`, `validation` and `test` Parquet files to `data/processed/all/` (or `high_value/`) and a summary to `reports/dataset_all.md` (or `dataset_high_value.md`).

Acceptance:
- Tests prove that changing later months, or the Kaggle label, does not change any feature.
- Tests prove no customer appears in more than one split.
- Window A and window B have identical feature columns.

Result on the real data (`reports/dataset_all.md`): 107 features.
Train 45,858 rows (4.65% churn), validation 9,812 (4.61%), test 9,677 (4.35%).
Our computed month 8 label and Kaggle's month 9 label give almost the same churn rate, which supports that our rule matches Kaggle's definition.
High-value only: 13,708, 3,024 and 2,942 rows.

## T5 - Features

**Owner:** Claude
**Status:** Done
**Depends on:** T4

Scope, in `src/prepaid_churn/features.py` (`FEATURES` holds a one-line description of each; `build_datasets` applies `add_features`):
- Recency across the window: `days_since_last_rech_window` and `days_since_last_rech_data_window`.
  Without a recharge in the current month, they add the current month's days to the previous month's value (T3 encodes "none" as the number of days in the month).
- `diff_<measure>` (current minus previous) for ARPU, outgoing, incoming and total minutes, data MB, recharge amount and recharge count.
- `trend_<measure>`: the current month's share of both months (0.5 = stable, 0 = dropped to zero); not for ARPU, which can be negative.
- `cur_onnet_share`, `cur_incoming_share` and their changes from the previous month, as dual-SIM signals from the proposal.
  Shares fall back to a neutral 0.5 when there are no minutes; the `no_voice_record` flag keeps that case visible.
- Night-pack and social-pack use were already columns (`night_pck_user`, `fb_user`), so they need no new feature.

Acceptance:
- Each feature has a unit test.
- No feature uses the label month (features only read `prev_` and `cur_` columns).

Result: 19 new features, 126 in total.
Medians in the train set, churners vs non-churners: 6 vs 3 days since the last recharge, `trend_total_og_mou` 0.35 vs 0.50, `diff_arpu` -89.5 vs +2.8.
The "receiving SIM" idea did not hold here: churners have a lower incoming share (0.30 vs 0.47), not a higher one; T7's feature importance will show whether the shares help at all.

## T6 - Training

**Owner:** Claude
**Status:** Done
**Depends on:** T5

Scope, in `src/prepaid_churn/training.py`:
- Logistic regression baseline: signed log transform (heavy-tailed amounts), scaling, no class weights.
- LightGBM, no class weights, deterministic mode, seed 42.
  The tree count comes from early stopping on 10% of the train customers, then LightGBM is refit on all train customers.
  This keeps the validation customers untouched for T7 (a change from the first plan, which early-stopped on validation).
- `churn train [--data-dir data/processed/all]` writes `artifacts/models/all/*.joblib` and `reports/training_all.md`.

Acceptance:
- Running `churn train` twice gives the same models (tested).
- Validation metrics for both models are in `reports/training_all.md`.

Result on the validation customers (uncalibrated), 12 seconds on a laptop CPU:

| Model | ROC-AUC | PR-AUC | Log loss | Brier |
|---|---|---|---|---|
| Logistic regression | 0.881 | 0.336 | 0.134 | 0.036 |
| LightGBM (288 trees) | 0.928 | 0.458 | 0.114 | 0.032 |

The churn rate is 4.6%, so a PR-AUC of 0.458 is about 10 times better than random.
The top feature is roaming outgoing minutes in the current month (13% of gain), then `trend_total_mou` and days since the last recharge.
Roaming is plausible (travel, moving away, or a local SIM abroad), and it is not leakage: it is measured in the month before the label month.

## T7 - Calibration and evaluation

**Owner:** Claude
**Status:** Done
**Depends on:** T6

Scope, in `src/prepaid_churn/evaluation.py`:
- For each model, choose none, sigmoid or isotonic calibration by 5-fold cross-validated log loss on validation customers (not by in-sample loss, which favours isotonic), then refit it on all validation customers.
- Champion: highest validation PR-AUC after calibration.
- Risk bands from validation only: `high` from the best-F1 threshold, `medium` above the validation churn rate, `low` below.
- `freeze` saves everything to `artifacts/models/all/champion.joblib` before the test window is scored.
- `churn evaluate` then scores test customers in window B once and writes `reports/evaluation_all.md`: metrics for both models, precision and recall at the top 5%, 10% and 20%, risk bands, a reliability table (instead of an image, so it reads in Markdown), and the high-value slice.

Acceptance:
- `reports/evaluation_all.md` compares logistic regression and LightGBM on window B.
- The report states the frozen thresholds and the date they were chosen (2026-09-19).

Result on the test window (months 7 and 8, Kaggle's month 9 label, unseen customers, 4.35% churn):

| Model | ROC-AUC | PR-AUC | Log loss | Brier |
|---|---|---|---|---|
| Logistic regression | 0.870 | 0.277 | 0.134 | 0.036 |
| LightGBM (champion) | 0.891 | 0.348 | 0.126 | 0.034 |

- Contacting the riskiest 10% catches 61.5% of churners at 26.8% precision; the riskiest 20% catches 79.8%.
- Risk bands: `high` 450 customers with 38.4% churn, `medium` 1,238 with 11.9%, `low` 7,989 with 1.3%.
- Calibration: LightGBM without class weights was already well calibrated (sigmoid and none tie at 0.1142 log loss).
  On test, the mean prediction is 4.22% against 4.35% observed, and the top tenth predicts 29.2% against 26.8% observed.
- High-value slice: ROC-AUC 0.906, PR-AUC 0.383 at 2.9% churn.
- Test is lower than validation (ROC-AUC 0.928, PR-AUC 0.458): it is a later month, Kaggle's label instead of ours, and unseen customers.
  This gap is the honest estimate of production performance.
- After the first run, the report was regenerated once only to print customer counts as whole numbers; the choices are frozen and deterministic, so no number changed.

Success thresholds (decision 13), checked against these test results:

| Threshold | Required | Result | Pass |
|---|---|---|---|
| Churners in the riskiest 10% | at least 50% | 61.5% | yes |
| PR-AUC vs churn rate | at least 3 times (0.131) | 0.348 (8.0 times) | yes |
| PR-AUC vs logistic regression | higher than 0.277 | 0.348 | yes |
| Mean predicted vs observed churn | within 1 point | 4.22% vs 4.35% (0.13 points) | yes |

The thresholds were written down after this test run, at the instructor's request, so this pass is reported honestly as a check, not as a pre-registered result.
From now on they are a gate for every new model (retraining, a new month or an operator's own data), checked before the model is used (T8).

## T8 - Model bundle and batch scoring

**Owner:** Claude
**Status:** Done
**Depends on:** T7

Scope:
- One versioned bundle in `artifacts/`: cleaning and feature pipeline, model, calibrator, threshold, data contract version, training metadata and metrics.
- Everything a scoring run needs travels inside the bundle: the feature list, fill values, the SHAP background sample and one stored sample row.
  Nothing is computed from the batch being scored, so one customer scored alone gets the same answer as inside a batch of ten thousand (a lesson from `Ali_Branch`, where three serving bugs only appeared on one-row batches).
- The bundle records the scikit-learn and LightGBM versions it was built with; loading it under other versions stops with a clear error.
- Loading runs a smoke prediction on the stored sample row; a bundle that loads but cannot predict is refused.
- `churn score --input <csv> --output <file>` validates the input against the data contract, scores every customer and writes the **subscriber output contract** from decision 10:
  subscriber ID (pseudonymous, decision 17), calibrated churn probability, risk band, top three reasons in plain language (from SHAP values), model version and scoring time.
  Customers already silent in the current month are not scored by the model; they get the risk band `already_silent` (decision 12).
  T10 and T11 later add the value tier and the recommended offer to the same rows.
- A Python function `score(df)` returns the same rows, so a teammate's service can call the model without files.
- The output contract is documented in `docs/output_contract.md`, generated from code like the data contract.
- Release gate: T7's evaluation computes the four success thresholds (decision 13) and stores the result with the champion.
  The bundle is only built from a champion that passes all four; otherwise the command stops and names the failed thresholds.

Acceptance:
- End-to-end test: a small valid CSV scores successfully.
- An invalid CSV is rejected by the schema before scoring.
- A test checks every output row against the output contract.
- A test shows the bundle is refused for a champion that fails a threshold.
- A one-row batch gives the same probability and reasons as the same row inside a larger batch, and its reasons are not all zero.
- A bundle whose smoke prediction fails is refused.

Findings:
- Commands: `churn evaluate` now also stores the release gate (`artifacts/models/all/gate.json`) and adds the four thresholds to `reports/evaluation_all.md`; `churn bundle` packages the champion; `churn score` writes `artifacts/scores/scores.csv`; `churn output-contract` writes `docs/output_contract.md`.
- `churn evaluate` was rerun once, only to store the gate: `champion.joblib` is byte-identical (same SHA-256) and every T7 number is unchanged; the report only gained the thresholds section.
- The bundle `lightgbm-2026-09-19-ef9430fb` is `artifacts/bundle/manifest.json` (plain JSON: library versions, data contract fingerprint, gate, thresholds, features) plus `model.joblib`.
  Loading checks the versions before unpickling anything, then predicts a stored sample row and refuses a bundle whose answer changed.
- `churn score` defaults to Kaggle's `test.csv`: 30,000 customers never used for training or evaluation, which stand in for "this month's base".
  In 10 seconds: 1,209 high, 3,594 medium, 22,779 low and 2,418 already silent; the mean prediction among active customers is 4.14% (test churn rate 4.35%).
- Reasons are exact SHAP values from LightGBM's own `pred_contrib`, which needs no background sample, so `Ali_Branch`'s "every reason is zero" bug cannot happen here.
  Computing them on all cores gives identical numbers 9 times faster (55 to 10 seconds for 30,000 customers).
  The most frequent top reasons are days since the last recharge, the amount on the last recharge day and outgoing roaming minutes.
- A one-row bug was found and fixed: pandas 3 gives an all-empty text column the type `object` in a one-row batch and `str` in a larger one; text columns now have an explicit type, and a test compares each customer alone with the full batch.
- Nothing is computed from the scored batch except the month end date, which the data contract already requires on at least one row.
- Data contract: `id` may now be a number or text, so an operator can export a salted hash of the phone number (decision 17); `docs/data_contract.md` was regenerated.
- `shap` was removed from the dependencies (LightGBM computes SHAP itself), and with it numba, llvmlite, slicer and tqdm.

## T9 - Documentation

**Owner:** Ali
**Status:** Done
**Depends on:** T8

Scope:
- README with setup, data, every command and the full pipeline run.
- Model card, starting from `Ali_Branch`'s `docs/model_cards/TEMPLATE.md`: data, churn definition, windows, metrics, success thresholds and their results, the human approval step, the Almadar view and its assumptions (decision 16), and limitations (single 4-month window, undocumented data provenance, behaviour from another market, educational license).
- The employee copilot indexes these documents (decision 17), so every fact in them names its source and date.

Acceptance:
- A teammate reproduces the evaluation report from a fresh clone by following the README only.

Findings (2026-09-21):
- [docs/model_card.md](docs/model_card.md) is written, adapted from `Ali_Branch`'s template (port log step 11).
- Every figure in it is copied from a committed report and names that report, because the copilot indexes the document (decision 17).
- It states what the model may not be used for first: no pricing, no credit or limits, no decision without a named reviewer, nothing sellable, and no language model in any path that sets an offer or a price.
- Limitations are explicit: another market, undocumented provenance, four months of history, an educational licence, a spent test window, no causal claim and no network-quality features.
- Ethics, selection bias and maintenance are covered; `circle_id` is the only region field and it is dropped before training, checked on 2026-09-21.
- No naive-versus-honest table is invented. Instead the card shows validation PR-AUC 0.4582 against test 0.3477 and names the four traps the design avoids.
- **Acceptance met.** A fresh clone of `Ali_Branch` on 2026-09-21 ran the README pipeline and reproduced every committed report byte for byte, with `git status` clean.
- The same run rebuilt bundle `lightgbm-2026-09-19-ef9430fb` and tier artifact `tiers-v1-cd15525cb3ef`, which confirms the T21, T15, T14 and dependency changes did not move the frozen champion.
- The README already listed every command; the full-pipeline block now also runs `fit-tiers` and `tiers`, which the service and the app need, and links the model card.
- `tests/test_model_card.py` compares the card's figures against the reports, so a stale number fails the suite instead of reaching the copilot.
- 16 new tests; 341 prepaid tests, lint and formatting pass.
- Scoring the 30,000 unlabeled customers with the real bundle gives high 1,209, medium 3,594, low 22,779 and already silent 2,418 (fresh clone, 2026-09-21).

## T10 - Value tiers (syllabus Ch 6)

**Owner:** Ali (implementation with Codex)
**Status:** Done
**Depends on:** T8, T18

Scope:
- Prepaid value scores per customer, from the two feature months only, adapted from `Ali_Branch`'s prepaid RFM (`src/cvm/features/rfm_le.py`):
  recency (days since last recharge), frequency (recharge count), monetary (recharge amount in LYD, from T18), tenure (age on network) and engagement (how many of voice, data, packs and roaming a customer uses).
- Rule-based tiers from score quintiles, readable by a business user; this is `value_tier` in the output contract.
- 12-month value in LYD: monthly value times the expected months kept, from the calibrated churn probability, capped at 12 months.
  T11 uses it.
- K-Means on the scaled scores with k chosen by silhouette score, a dendrogram (hierarchical clustering) on a sample, and a PCA 2-D plot of the clusters, adapted from `Ali_Branch`'s `src/cvm/models/m2_value/segmentation.py`.
- A short, honest comparison of rule-based tiers vs clusters.
  If the silhouette shows no clear structure, the report says the tiers are a reporting convention, not a discovered structure (as `Ali_Branch` found on its data).
- `churn tiers` command.

Acceptance:
- Every customer gets exactly one tier.
- Tiers are computed without the label month.
- Plots and the comparison are in `reports/tiers.md`.

Findings (2026-09-20):
- Adapted Ali's five-dimension prepaid RFM and exploratory clustering design to the existing two-month windows (decision 19; port log step 7).
- Training-frozen dimension and composite cutoffs, the T18 LYD rate and a version fingerprint are saved in `artifacts/tiers/tiers.json`.
- Ties are preserved, constant dimensions stay neutral, and a subscriber receives the same output alone, reordered or in a batch.
- The full `churn tiers` path extends the T8 output using the same export and a gated bundle; `--tiers-only` explicitly leaves risk-dependent scenarios unavailable.
- Already-silent customers receive a tier but no invented probability or value estimate.
- The 12-month revenue scenarios and hazard sensitivities are documented assumptions, not validated CLV or measured offer savings.
- The training fit uses 45,858 customers; every one of the 30,000 unlabeled export customers receives one of the five tiers.
- K-Means selects k=2 with silhouette 0.2766, showing weak separation; adjusted Rand agreement with tiers is 0.2702.
- `reports/tiers.md` contains the comparison, training cutoffs, illustrative value scenarios, PCA plot and sampled Ward dendrogram.
- Tests cover absent/invalid inputs, ties, missing activity, silent customers, ID preservation, artifact corruption, future-field exclusion, single-customer consistency and CLI integration.
- 202 prepaid tests pass; lint, format and locked offline sync pass.
- No churn model was retrained, no real-data test evaluation was repeated, and no raw or customer-level artifact was added to Git.

## T11 - Retention decision layer

**Owner:** Ali (implementation with Codex)
**Status:** Done
**Depends on:** T8, T10, T16, T18

Scope:
- Action space: the real Almadar catalogue (T16) plus "no offer".
  "No offer" wins whenever no offer has a positive expected value, and the report says how often that happens.
- Expected value per customer and offer: churn probability x share of churners the offer saves x 12-month value (T10) - offer cost.
  The share saved and every cost are assumptions in one config file and are printed in the report; none is presented as a measured fact.
  Costs use the delivery cost estimates from T16 and are labelled as estimates.
- Offers prefer Almadar's own off-peak and bonus-data products (for example the 1 LYD morning pass, 06:00 to 11:00) over price discounts.
- Guardrails, adapted from `Ali_Branch` (`src/cvm/decision/`):
  - a per-customer spend cap relative to the customer's value;
  - a total budget filled greedily by expected net value;
  - no offers to low-risk customers;
  - a cannibalisation guard keyed on the bundle a customer holds (T18): a cheap unlimited offer is never proposed to a customer on a monthly bundle above the base rung (نت 20, 35 LYD), because it can pull them down to a cheaper package.
- The report compares the targeted campaign with treating everyone **at the same spend**, and with targeting by churn risk alone.
  (Lesson from `Ali_Branch`: comparing campaigns with different budgets measures the budget, not the targeting.)
- A random holdout group (default 10%) that gets no offer, so a real campaign can measure the true effect later.
- Each subscriber row gets `value_tier`, `recommended_offer_id` and a plain-language `offer_reason` in Arabic and English, extending the T8 output contract.
- A decision log with the reason for every offer.
- Human approval step (decision 14):
  - `churn decide` only writes **proposals** (status `proposed`), each with customer ID, offer, reason, expected cost and expected value.
  - A named reviewer approves or rejects proposals, one by one or the whole list, with `churn approve --proposals <file> --reviewer <name>` (and later from the T14 app).
  - Only approved rows go into the released campaign file that the chatbot and any sending system read; rejected and unreviewed rows never leave.
  - The decision log records the reviewer, the time, the decision and an optional note for every proposal.
- `churn decide` and `churn approve` commands.

Acceptance:
- Tests for each guardrail, including the cannibalisation guard.
- Holdout assignment is random, reproducible with a seed, and never receives an offer.
- Tests show that unapproved or rejected proposals never appear in the released campaign file, and that every approval is logged with a reviewer name.
- `reports/decisions.md` states every assumption next to the results, including the equal-spend comparison.

Findings (2026-09-20):
- `retention.py` follows the existing pure-function and thin-CLI patterns, adapting Ali's guardrails, budget comparison and decision-log design (decision 20; port log step 8).
- `data/almadar/retention.toml` declares the budget, per-customer campaign cap, holdout, saved-share assumptions and delivery-cost estimates in one file.
- Decisions use the same raw export for gated risk, frozen value and the mapped held bundle; no model is trained or reevaluated.
- Only positive-value catalogue bonuses can be proposed; no offer is explicit for low risk, inactivity, unavailable risk, holdout, guard failures, nonpositive value and budget exhaustion.
- Cheap unlimited products are blocked above the 35 LYD base monthly rung; unknown 5G and family eligibility also excludes a product.
- Costs and budgets use integer dirhams, with conservative rounding; allocation is deterministic greedy net-value ordering.
- The report compares untargeted and risk-only allocation at the exact targeted spend in expectation, with fractional counts only in diagnostic baselines.
- Seeded hash holdouts are stable across ordering and batches; 2,965 of the 30,000 real export rows were assigned to holdout.
- `campaign.py` stores input, catalogue, policy and proposal snapshots with a fingerprint, plus named review events.
- `churn approve` reviews selected IDs or all pending proposals, supports rejection and notes, and releases only approved rows without internal risk/value fields.
- CSV edits cannot approve offers, reviews are serialized with a lock, JSON writes are atomic, and `--refresh` recovers derived files without approving pending rows.
- All 30,000 real-export rows received a decision; the report is explicitly a no-bundle readiness run with zero offers and no effectiveness claim.
- 247 prepaid tests, lint and formatting pass; tests use hand-made data, including the full bundle-to-decision path and positive approval/rejection scenarios.
- No real customer campaign was approved, sent or released; no customer-level artifacts were committed.
- Local reviewer names are not authentication, and caps are per campaign rather than annual; T15 and a future spending ledger must address those boundaries before shared operational use.

## T12 - Sequence benchmark (syllabus Ch 8, Ch 9 RNN)

**Owner:**
**Status:** Todo
**Depends on:** T7

Scope:
- A Keras LSTM over the monthly steps of each window, with dropout and early stopping on validation customers.
- Calibrate it the same way as T7 and compare it with LightGBM on the same frozen test.
- Explain the result honestly: with only two monthly steps per window, LightGBM is expected to win.
- TensorFlow goes in the `experiments` dependency group.

Acceptance:
- `reports/sequence_benchmark.md` with the comparison table and a written verdict.

## T13 - Synthetic data experiment (syllabus Ch 9 GAN)

**Owner:**
**Status:** Todo
**Depends on:** T4, T18

Question: can an operator share a synthetic copy of its customer data (real data cannot leave the operator) and still get a useful model?

Scope:
- Reuse `Ali_Branch`'s synthesis engine (`src/cvm/synthesis/ctgan_engine.py`) and quality gate (`quality_gate.py`), refit on window A train customers only instead of Cell2Cell.
  So the synthetic customers' churn is learnt from real behaviour, not drawn from a formula.
- CTGAN, with a Gaussian copula as a simple baseline.
- Train on synthetic, test on real validation customers; compare with train on real.
- Detection test: a classifier that tries to tell real from synthetic rows (lower ROC-AUC means more realistic).
- SDMetrics quality report.
- The synthetic copy can be shown in Almadar terms through T18, which makes it a shareable "synthetic Almadar customer base" for demos.
- SDV goes in the `experiments` dependency group; its Business Source License allows non-production use.

Acceptance:
- `reports/synthetic.md` with the train-on-synthetic vs train-on-real table and the detection ROC-AUC.
- The synthetic data is never used to train the production model.

## T14 - Demo app

**Owner:** Ali
**Status:** Done
**Depends on:** T8, T11

Scope:
- One Streamlit app, adapted from `Ali_Branch`'s Command Center (`apps/`):
  - Overview: customers and LYD at risk by risk band and value tier, the model version and its test results.
  - Subscriber view: churn probability, top reasons, value tier, the Almadar bundle held and the proposed offer for one customer.
  - Campaign builder: set a budget, see the proposed customers, holdout size, expected cost and value, and the equal-spend comparison, then approve or reject proposals under a reviewer name (the T11 approval step).
  - Customer message preview: the Arabic text of an approved offer as the customer would see it by SMS or in the chatbot.
- It reads the model bundle and decision output; it contains no model logic of its own.

Acceptance:
- `uv run streamlit run ...` starts the app from the README instructions.
- Every screen is opened in a browser and checked, including with a single customer.
  (Lesson from `Ali_Branch`: two of its late bugs were only visible on screen.)

Findings (2026-09-21):
- Four screens in `app/`, over the pure `src/prepaid_churn/demo.py`; loading goes through `service.load_state`, so the app and the T15 endpoints answer from one state.
- Start it with `uv run streamlit run app/Home.py`; `PREPAID_CHURN_CAMPAIGN_DIR` and `PREPAID_CHURN_PORTFOLIO` choose which campaign and export to show.
- The app recomputes nothing. Its only write is a review, through `campaign.review_file`, with the same lock, atomic replacement and named audit event as `churn approve`.
- The budget control is an explicit preview over the campaign's own stored inputs; it is never written and nothing in it can be approved (decision 22).
- Every screen was opened in a browser on 2026-09-21: against the real 30,000-row export, a five-customer campaign and a one-customer campaign.
- The browser check found five defects the unit tests had not, all now fixed: an alphabetically sorted axis that put the value tiers in a meaningless order, a typed ID silently overriding the random-pick button, fractional tick marks for whole customers, "1 customers", and "reviewed by nan" on an unreviewed proposal.
- Approving on screen was verified end to end: the reviewer name is required, `review_log.jsonl` records subscriber, reviewer, decision, UTC time and campaign fingerprint, and only the approved row reaches `released.csv`.
- The SMS preview reports parts rather than characters alone. The approved message on the checked campaign is 102 characters and sends as **two** UCS-2 parts, so T11's reason text does not fit one SMS in Arabic; that is a real finding for T11 to consider, not a display detail.
- The customer message carries no churn probability, risk band, value figure or reviewer name.
- The subscriber screen refuses an ID shaped like a Libyan mobile number before any lookup, which was checked in the browser.
- 26 new tests; 325 prepaid tests, lint and formatting pass.
- `streamlit` is added as a dependency; charts use Altair, which Streamlit already installs.
- Limitations: outputs are cached per session and reread after a review or a restart, and the app is a local development server, not a deployed one.

## T15 - Integration service for the chatbot and copilot

**Owner:** Ali
**Status:** Done
**Depends on:** T8, T11

Part of the MVP (decision 17): the chatbot and copilot call this service; they never import the package or read its files.

Scope:
- A small FastAPI app that only reads the latest released outputs; it has no model logic, and nothing can be created, changed or approved through it.
- Endpoints:
  - `GET /health`: bundle loaded, smoke prediction passed, date of the latest outputs.
  - `GET /catalogue`: the Almadar packages (T16), for the chatbot.
  - `GET /subscribers/{id}/retention`, for the chatbot: the offer and its reason only if a reviewer approved it (T11), never the churn probability; 404 when there is no approved offer.
  - `GET /portfolio/summary`, for the copilot: customers and LYD at risk by risk band and value tier, plus the model version, its test metrics and the success-threshold results.
- Access control: separate API keys for the chatbot and the copilot, each accepted only on its own endpoints.
- De-identification: IDs are pseudonymous.
  The API rejects IDs shaped like a Libyan phone number (pattern from `Ali_Branch`'s privacy check), and a `pseudonymize` helper (salted SHA-256, from `Ali_Branch`'s `src/cvm/ingest/hashing.py`) is provided for operators to hash phone numbers before export.
- Response models match the output contract, so the OpenAPI page at `/docs` doubles as the integration documentation.

Acceptance:
- Tests call every endpoint with FastAPI's test client, including with a wrong key and with a phone-number ID.
- A test shows the chatbot endpoint never returns a churn probability or an unapproved offer.

Findings (2026-09-21):
- `service.py` holds the pure read-only state and the four payload builders; `api.py` is the thin FastAPI layer; `privacy.py` is the ported identifier check.
- Every route is a GET, and a test asserts the generated OpenAPI document contains no other method, so the service has no write path.
- Approved offers are read from the authoritative `proposals.json` through `released_campaign`, never from the derived `released.csv`, so a hand-edited CSV still cannot publish an offer.
- One key per consumer in the `X-API-Key` header, compared in constant time; the copilot key is refused on chatbot endpoints and the chatbot key on `/portfolio/summary`.
- Both keys come from the environment with no default, must be at least 24 characters and must differ; the service refuses to start otherwise (decision 21).
- `/health` needs no key, reports bundle loaded and smoke prediction separately, and is `ok` only when the bundle predicts and a portfolio exists.
- The chatbot response model forbids undeclared fields, and omits the churn probability, the risk band, every value figure and the reviewer's name.
- Rejected, unreviewed, unproposed and unknown subscribers all return the same 404 message, so no one can infer that an offer was considered and refused.
- An ID shaped like a Libyan mobile number is refused with 422; a salted SHA-256 digest is looked up normally, checked over 500 generated digests.
- `lyd_at_risk` is value weighted by churn probability, and is null rather than zero when an export carries no risk estimate.
- 52 new tests; 299 prepaid tests, lint and formatting pass.
- Run against this checkout on 2026-09-21: degraded with no bundle, all 57 packages served, 30,000 subscribers summarised with `risk_available` false, zero approved offers.
- Limitations: outputs are loaded once, so a new release is served after a restart; the keys are service-to-service access control, not per-user authorization, and assume the service is not exposed publicly.
- T20 still owns `docs/integration.md`, the example client and the walkthrough with the chatbot and copilot owners.

## T16 - Almadar catalogue and market facts

**Owner:** Claude
**Status:** Done
**Depends on:** nothing

Why: the retention offers (T11) and the team's customer chatbot both need the real prepaid packages, and Ali collected Almadar's (decision 16).

Scope:
- Keep Ali's Almadar source files unchanged in `data/almadar/source/`.
- `data/almadar/offers.csv`, one row per package: offer ID, operator, family, Arabic and English name, price in LYD, validity, data volume or unlimited, minutes, speed caps, time window, where the volume comes from, source row and collection date.
  It holds only what the operator sells, so the chatbot can read it as is.
- `data/almadar/market.toml`: recharge cards, pay-as-you-go tariffs, the two emergency credit products, the ARPU assumption and the delivery cost estimate, each with its status (confirmed, reported, assumption or estimate) and source.
  TOML instead of YAML, because Python reads it without a new dependency.
- A loader and validation in `src/prepaid_churn/almadar.py`, and `docs/almadar.md` explaining the files and how to refresh them (prices change, so every row keeps its collection date).
- Libyana can be added later as rows with its own operator value.
- Share `offers.csv` with the chatbot owners: it is the action plan's "Offer / Package Catalogue".

Acceptance:
- Every row has a source and a collection date.
- A test validates the files: required columns, positive prices, known operator, unique IDs, and a status on every market value.
- The package count matches `Ali_Branch`'s catalogue (37 packages in 12 families), or the difference is explained.

Findings (details in `docs/almadar.md`):
- 57 packages in 17 families, all from the operator's own file; `check_against_source` proves every family, name, price and stated value still matches it, row by row.
- The 20 extra packages against `Ali_Branch` are the five Mix families (data and voice), which Ali removed in commit `62040af` without saying why; they stay until he says the operator no longer sells them (a test pins the difference).
- Data volumes: 31 packages state them, 17 are read from the name ("نت 20" is 20 GB), 6 are reported as unlimited by `Ali_Branch` (Silver and hourly 5G), and 3 are unknown (Social).
- Only one package has a time window: the 1 LYD morning pass, unlimited data and voice from 06:00 to 11:00.
- The recharge cards are `reported` (no operator document yet); ARPU (40 LYD) is an assumption and delivery costs are estimates.

## T17 - Uplift experiment on real data

**Owner:**
**Status:** Todo
**Depends on:** nothing

Why: the SIC action plan lists the Orange Belgium Churn-Uplift dataset, and a retention offer only pays when it changes behaviour (decision 4).

Scope:
- Reuse `Ali_Branch`'s two-model uplift and Qini code (`src/cvm/models/m3_uplift/`), whose Qini was checked against scikit-uplift.
- Orange Belgium, from OpenML (dataset 45580): 11,896 customers, 178 anonymized features, a phone retention campaign with a random control group (about 76% treated, 24% control), churn about 3.5%.
- Criteo Uplift, as in `Ali_Branch` (a 10% sample; held-out Qini 0.0771 there): a large randomized trial, but advertising, not telecom.
- Compare targeting by churn risk with targeting by uplift, using Qini curves on held-out customers.
- Write the lesson for T11's "share saved" assumption in `reports/uplift.md`.
- Limits to state: Orange is postpaid with anonymized features that cannot be combined with our model; Criteo is advertising; both licenses are non-commercial.

Acceptance:
- `reports/uplift.md` with the Qini comparison for both datasets and a written verdict.

## T18 - Almadar view of the real customers

**Owner:** Claude
**Status:** Done
**Depends on:** T4, T16

Why: decision 16; value, offers, emergency credit and the app speak Almadar's money and packages, while the churn model stays on real behaviour.

Scope, in `src/prepaid_churn/almadar.py`:
- One scale factor from the source currency to LYD, anchored on Almadar's ARPU assumption in `data/almadar/market.toml`, so the shape of real spending is kept.
- Monthly value in LYD from the current month's recharges.
- Usual recharge card: each customer's typical recharge mapped to the nearest Almadar card (5, 10, 20, 40 or 100 LYD).
- Bundle held in the current month: customers with a monthly data pack (upGrad `monthly_2g`, `monthly_3g`) get the Almadar monthly bundle their data spend in LYD would buy; customers with only short packs (`sachet_2g`, `sachet_3g`) get a daily pack; the rest are pay-as-you-go.
- Uses only the feature months of a window, never the label month.
- `churn almadar-view` writes the view for a dataset and `reports/almadar_view.md` with the distributions, the share on each bundle and every assumption.

Acceptance:
- Unit tests for each mapping rule on hand-made frames.
- The report lists every assumption with its status.
- The view never changes a churn feature or the model.

Findings (`reports/almadar_view.md`, rules in `docs/almadar.md`):
- Taha chose the 40 LYD ARPU on 2026-09-19.
  The rate is 40 LYD over 537.17, the mean monthly recharge of the 64,509 customers active in month 8 of `train.csv` (stored in `market.toml` as a measured fact), so 1 unit of the source currency is 0.074464 LYD.
- On the scoring base (Kaggle's `test.csv`, 27,582 active customers): mean spend 39.39 LYD a month, median 22.08, 10th percentile 5.21, 90th percentile 82.13.
- For 88.9% of active customers the nearest card to their usual airtime recharge is the smallest, 5 LYD, and for 9.1% it is 10 LYD; small top-ups dominate, as `Ali_Branch` argued.
- Bundles held: 71.3% pay-as-you-go, 14.4% a monthly bundle (mostly Net 6, the floor for small data spend) and 14.3% a daily pack.
- A test changes month 8 and checks that a window A view does not move; breaking the code to read month 8 makes it fail.

## T19 - Emergency credit advice

**Owner:** Ali
**Status:** Done
**Depends on:** T16, T18

Why: Almadar's two emergency credit products (an airtime advance of 1, 3 or 5 LYD and a 5 LYD data advance) are the most Libyan part of Ali's work, and a safe limit can be set from real recharge behaviour.

Scope:
- Rule-based advice, adapted from `Ali_Branch`'s `conf/advance.yaml` and `src/cvm/decision/advance_limit.py`: never advance more than the customer's usual recharge card can clear (affordability ceiling).
- State the zero-residual finding from `Ali_Branch`: the 5 LYD data advance equals the smallest 5 LYD card, so clearing it leaves the customer at zero balance; the smaller airtime advances avoid this.
- No repayment model: no real repayment data exists (decision 15).
- Advice is a proposal for a person, like offers (decision 14).

Acceptance:
- Tests for the ceiling and the denominations.
- `reports/emergency_credit.md` with the share of customers per advised limit and every assumption.

Findings (2026-09-21):
- `src/prepaid_churn/advance.py` advises a limit and grants nothing; `churn advance` writes the advice and the report.
- One rule: never advise a debt above 0.6 of the customer's typical top-up, ported with Ali's reason, and the code refuses any fraction at or above 1.
- Only denominations the operator sells are advised, so a 2.9 LYD ceiling advises 1 LYD rather than inventing a 2 LYD advance.
- The zero-residual finding is computed from `market.toml`, not hardcoded: the smallest card, the data advance and the top airtime rung are all 5 LYD, so clearing either leaves 0 LYD.
- A test shows the finding would retire itself if the operator ever sold a larger smallest card.
- The basis is an adaptation. Ali asks for the modal top-up; this data has only monthly totals and counts, so the quieter month's average per recharge is used, which is never larger and so cannot widen the advice.
- That choice moves the result by more than twenty points, so the report carries a sensitivity table across the quieter month, the mean and the busier month, and both months travel beside each verdict.
- **The result is a finding about the product.** This base tops up often in very small amounts, with a median typical top-up of 1.89 LYD against five to six recharges a month.
- The smallest advance needs 1.67 LYD to clear while leaving balance, so 46.1% of customers are advised nothing; the flat 5 LYD data advance needs 8.33 LYD and is advised for 4.65%, though the operator offers it to anyone with a low balance.
- Advised airtime limits: 1 LYD for 37.51%, 3 LYD for 11.70%, 5 LYD for 4.65%, declined for 46.14%; 0.90% had no recharge at all.
- Not ported, each for a stated reason: the repayment model, tier ceiling, CLV cap, cooling-off, chronic distress, lockout step-down, reject inference and fee structure.
- 38 new tests; 379 prepaid tests, lint and formatting pass. No new dependency.

## T20 - Integration check with the team platform

**Owner:** Taha + Claude
**Status:** In review (the guide, the client and the check are done; the owners have not confirmed)
**Depends on:** T15

Why: the final goal is one platform (decision 17), and `Ali_Branch` noted that nobody had ever called its API from the other side.

Scope:
- `docs/integration.md` for the chatbot, copilot, network ML and GIS owners, adapted from `Ali_Branch`'s `docs/INTEGRATION.md`:
  - endpoints with request and response examples, API keys and pseudonymous IDs;
  - the grounding rules for LLM consumers: never set a price, offer or limit; never invent a number; cite the response field; refuse rather than guess; never cache an offer;
  - which documents the copilot may index;
  - the future field contract for per-subscriber network quality from network ML.
- A small example client (a chatbot lookup and a copilot summary).
- A contract test that runs the example client against the app.
- Walk through it with the chatbot and copilot owners (Taha and Ali) and record what they still need.

Acceptance:
- The example client works against a running service, following the README.
- The chatbot and copilot owners confirm in this ticket's Findings that the responses give them what they need.

Findings (2026-09-21):
- [docs/integration.md](docs/integration.md) is written for four owners at once: it says why the seam is HTTP rather than an import, how to start the service, what each endpoint answers with real captured responses, the six grounding rules for components that use a language model, which files a retriever may index and which it may never touch, and what this module would need from network ML.
- Every example in it was captured from a running service, not written by hand; the guide is checked against the live OpenAPI document by a test, so a route or a key it misses fails the suite.
- `src/prepaid_churn/client.py` is the example, written to be copied rather than imported: standard library only, keys and base URL as arguments, no dependency added on either side (decision 25).
- `churn check-integration --url <url> --subscriber-id <id>` runs it and prints what each consumer sees, including the four refusals: the copilot's endpoint with the chatbot key (403), a chatbot endpoint with the copilot key (403), no key at all (401) and an ID shaped like a Libyan phone number (422).
  It exits 1 when a refusal did not happen.
- Run on 2026-09-21 against a service holding the 30,000-subscriber base, the gated bundle and a campaign with two approved offers and one rejected: status ok, 57 packages, `SABAH_1` returned for subscriber 70008 with its Arabic reason, 176,494 LYD at risk across the bands, 4 of 4 success thresholds passed, and every refusal correct.
- The contract test starts the real app on a real port and calls it over a socket, rather than in process as `test_api.py` does, because the seam is the thing this ticket proves.
- 9 new tests; 388 prepaid tests, lint and formatting pass.
- The network ML contract is keyed by the pseudonymous subscriber ID rather than by `cell_id` as `Ali_Branch` had it, because this module never sees a cell; it also states that adding any such field means a new frozen champion, so it is a version 2 change.
- For the antenna and cell placement owners the honest answer is that we have nothing per cell to give; the guide says so rather than implying a join that nobody can make.
- **Still open:** the walkthrough itself. Taha owns the chatbot and the copilot in the action plan, and the acceptance needs him and the other owners to call the service and answer in this section.

## T21 - Code and logic review

**Owner:** Ali (review requested and implemented with Codex)
**Status:** Done
**Depends on:** T2, T3, T7, T8

Scope:
- Review `tahaDev` and deliver fixes only on `Ali_Branch`, preserving the source coding style and methodology (decision 18).
- Fix invalid input acceptance, identifier corruption, stale derived flags and bundle consistency checks.
- Remove redundant prediction work without changing calibrated outputs or frozen choices.
- Review GIS and the legacy modules, implement independent correctness/performance fixes and document modelling follow-ups.

Acceptance:
- Synthetic regressions reproduce the original defects and pass after the fixes.
- Lint, format checks and the full prepaid test suite pass.
- GIS tests pass, and batched density queries match the original counts.
- Valid real exports retain the same model features in both windows.
- Findings, benchmark limits and bundle migration steps are documented in [../CODE_REVIEW.md](../CODE_REVIEW.md).

Findings:
- 170 prepaid tests and 21 GIS tests pass; lint and formatting are green.
- The stricter schema accepts both committed raw exports, with identical model features.
- Calibration uses two model prediction calls instead of five; the focused density benchmark is 4.00 times faster.
- The frozen champion choices and real-data test results are unchanged.
- No new infrastructure, dependencies or business logic were introduced.

## Future work (needs real operator data)

- Airtime advance limits learnt from repayment history (T19 is the rule-based first step).
- Network-quality features (dropped calls, outages) from the network ML team, through the T20 field contract.
- Uplift models on our own customers, once a campaign with a holdout group has run.
- Retraining on Almadar's own export, which is what a commercial deployment requires (decisions 11 and 16).
