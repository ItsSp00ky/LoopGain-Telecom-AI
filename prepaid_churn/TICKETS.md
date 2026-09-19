# Tickets

Work plan for the prepaid churn module.
Pick a ticket by writing your name in its **Owner** field.
A ticket is done only when its acceptance criteria pass and `ruff check`, `ruff format --check` and `pytest` are green.
The reasons behind every decision are in [docs/decisions.md](docs/decisions.md).

## Handoff

Update this section at the end of every working session.

**Last updated:** 2026-09-18 by Taha + Claude.

**Status**
- T0 and T1 are done.
- The data is committed in `data/raw/` (`train.csv`, `test.csv`, `data_dictionary.csv`), so a fresh clone can run everything (decision 9).
- `reports/profile.md` holds the real-data profile; the T1 Findings below summarise it.

**Blocked on**
- Nothing.

**Next steps, in order**
1. Decide the eligibility question below (it changes T4 and every metric after it).
2. T2 and T3 can run in parallel now; T3's rules are confirmed by the T1 Findings.
3. Then T4.
   T10 and T13 only need T4, so they can start as soon as T4 is done.

**Open questions**
- **Eligibility (decide before T4):** 59.9% of month 9 churners were already inactive in month 8.
  Should the model score only customers who are active in the current month?
  Claude's recommendation: yes.
  Customers already silent are mostly gone (77.9% churn next month), predicting them adds no business value, and keeping them would inflate every metric.
  They get a simple "already silent" flag in reports instead.
  Among active customers the churn rate is 4.4%.

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
- **High-value filter:** optional flag, off by default.
  When on, it keeps customers whose average recharge amount over the two feature months is at or above the 70th percentile (the top 30%).
- **Models:** logistic regression baseline and LightGBM, with probability calibration.
  PCA is never a model input, because it destroys per-customer explanations.
  PCA is allowed only for the T10 segment plot.
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
  - Voice block: 35 minute columns always go missing together (agreement 1.0 with `onnet_mou`), for 3.9%, 3.8% and 5.3% of customers in months 6, 7 and 8.
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

## T2 - Input schema

**Owner:**
**Status:** Todo
**Depends on:** T1

Scope:
- A pandera schema that defines a valid prepaid monthly export: required columns, types, value ranges, allowed missing values.
- Validation runs on load and reports every problem with a readable message.
- The schema is written for the prepaid data contract, so a real operator export (for example Libyana or Al-Madar) can be checked against it later.

Acceptance:
- Loading a valid file passes.
- Tests show that missing columns, wrong types and out-of-range values fail with clear errors.

## T3 - Cleaning

**Owner:**
**Status:** Todo
**Depends on:** T1

Scope (rules confirmed by the T1 Findings):
- Voice block and data block missing values become 0.
- A "no voice record this month" flag from the voice block, because it marks a whole month without calls.
- `date_of_last_rech` and `date_of_last_rech_data` become "days since last recharge" at the month end, with an explicit value for "no recharge this month".
- Drop the 13 no-information columns listed in the T1 Findings, and `id` from the features.
- Negative ARPU: keep the values as they are and document why (billing adjustments; tree models handle them).

Acceptance:
- One unit test per rule on a small hand-made DataFrame.
- Cleaning twice gives the same result as cleaning once.

## T4 - Windows, labels and split

**Owner:**
**Status:** Todo
**Depends on:** T3

Scope:
- Turn month-suffixed columns into "previous month" and "current month" columns for window A and window B (`monthly_columns` in `data.py` already maps base names to months).
- Label function built on `usage_inactive` in `labels.py`.
- Eligibility rule for customers already inactive in the current month, as decided in the Handoff open question (T1: 59.9% of month 9 churners were already inactive in month 8).
- Optional high-value filter.
- Customer split 70/15/15, stratified by the window A label, with a fixed seed.
- `churn build-dataset` command that writes the processed windows to `data/processed/`.

Acceptance:
- Tests prove no feature column in either window is derived from the label month.
- Tests prove no customer appears in more than one split.
- Window A and window B have identical feature columns.

## T5 - Features

**Owner:**
**Status:** Todo
**Depends on:** T4

Scope:
- Month-over-month change for key usage and recharge measures (current minus previous, and ratio).
- Recency features from T3.
- Totals across voice and data.
- Prepaid signals from the proposal that the data really contains: on-net share of outgoing minutes, incoming-to-outgoing ratio (a "receiving SIM" sign of a second SIM), night-pack and social-pack use.
- Keep the list short and justified; every feature gets a one-line description.

Acceptance:
- Each feature has a unit test.
- No feature uses the label month.

## T6 - Training

**Owner:**
**Status:** Todo
**Depends on:** T5

Scope:
- Logistic regression baseline with scaling.
- LightGBM with early stopping on validation customers.
- No class weights, so the raw probabilities stay close to the real churn rate before calibration.
- `churn train` command with a fixed seed.

Acceptance:
- Running `churn train` twice gives the same models.
- Validation metrics for both models are written to `reports/`.

## T7 - Calibration and evaluation

**Owner:**
**Status:** Todo
**Depends on:** T6

Scope:
- Calibrate each model on validation customers and compare sigmoid and isotonic by validation log loss.
- Choose the operating threshold on validation customers only.
- Freeze model, calibrator and threshold, then evaluate once on test customers in window B.
- Report ROC-AUC, PR-AUC, log loss, Brier score, a reliability plot, and precision and recall at the top 5%, 10% and 20% of customers by risk.
- Report the same metrics for the high-value slice.
- `churn evaluate` command.

Acceptance:
- `reports/evaluation.md` compares logistic regression and LightGBM on window B.
- The report states the frozen threshold and the date it was chosen.

## T8 - Model bundle and batch scoring

**Owner:**
**Status:** Todo
**Depends on:** T7

Scope:
- One versioned bundle in `artifacts/`: cleaning and feature pipeline, model, calibrator, threshold, schema version, training metadata and metrics.
- `churn score --input <csv> --output <csv>` validates the input, scores every customer and writes probability, risk flag and top three reasons from SHAP values.

Acceptance:
- End-to-end test: a small valid CSV scores successfully.
- An invalid CSV is rejected by the schema before scoring.

## T9 - Documentation

**Owner:**
**Status:** Todo
**Depends on:** T8

Scope:
- README with setup, data download, every command and the full pipeline run.
- Model card: data, churn definition, windows, metrics, limitations (single 4-month window, undocumented data provenance, educational license).

Acceptance:
- A teammate reproduces the evaluation report from a fresh clone by following the README only.

## T10 - Value tiers (syllabus Ch 6)

**Owner:**
**Status:** Todo
**Depends on:** T4

Scope:
- Prepaid value scores per customer, from the two feature months only:
  recency (days since last recharge), frequency (recharge count), monetary (recharge amount) and tenure (age on network).
- Rule-based tiers from score quintiles, readable by a business user.
- K-Means on the scaled scores, with k chosen by silhouette score.
- A PCA 2-D plot of the clusters and a dendrogram (hierarchical clustering) on a sample, saved to `reports/`.
- A short comparison of rule-based tiers vs clusters.
- `churn tiers` command.

Acceptance:
- Every customer gets exactly one tier.
- Tiers are computed without the label month.
- Plots and the comparison are in `reports/tiers.md`.

## T11 - Retention decision layer

**Owner:**
**Status:** Todo
**Depends on:** T7, T10

Scope:
- Expected value per customer from the calibrated churn probability, the customer's value, the offer cost and a configurable "share of churners an offer saves".
  Every assumption lives in one config file and is printed in the report; none is presented as a measured fact.
- A small offer menu per tier, preferring bonus data (night or off-peak) over price discounts.
- Guardrails: a per-customer spend cap relative to the customer's value, a total budget filled greedily by expected net value, and no offers to low-risk high-value customers.
- A random holdout group (default 10%) that gets no offer, so a real campaign can measure the true effect later.
- A decision log with the reason for every offer.
- `churn decide` command.

Acceptance:
- Tests for each guardrail.
- Holdout assignment is random, reproducible with a seed, and never receives an offer.
- `reports/decisions.md` states every assumption next to the results.

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
**Depends on:** T4

Question: can an operator share a synthetic copy of its customer data (real data cannot leave the operator) and still get a useful model?

Scope:
- Fit CTGAN on window A train customers only, with a Gaussian copula as a simple baseline.
- Train on synthetic, test on real validation customers; compare with train on real.
- Detection test: a classifier that tries to tell real from synthetic rows (lower ROC-AUC means more realistic).
- SDMetrics quality report.
- SDV goes in the `experiments` dependency group; its Business Source License allows non-production use.

Acceptance:
- `reports/synthetic.md` with the train-on-synthetic vs train-on-real table and the detection ROC-AUC.
- The synthetic data is never used to train the production model.

## T14 - Demo app

**Owner:**
**Status:** Todo
**Depends on:** T8, T11

Scope:
- One Streamlit app with two pages:
  - Subscriber 360: churn probability, top reasons, value tier and chosen offer for one customer.
  - Campaign builder: set a budget, see selected customers, holdout size, expected cost and expected value.
- It reads the model bundle and decision output; it contains no model logic of its own.

Acceptance:
- `uv run streamlit run ...` starts the app from the README instructions.

## Future work (needs real operator data)

- Airtime advance limits (a learned replacement for a fixed eligibility rule).
- Network-quality features (dropped calls, outages) per cell site.
- Uplift models, once a campaign with a holdout group has run.
