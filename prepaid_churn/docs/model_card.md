# Model card - prepaid silent-churn risk

This card describes the only model this module puts into use.
It is written so the employee copilot can index it (decision 17), so every number below names the file it comes from and the date it was produced.
Nothing here is recalculated by hand: each figure is copied from a committed report that a fresh clone regenerates byte for byte.

| | |
|---|---|
| **Model** | Silent-churn risk for prepaid subscribers |
| **Bundle version** | `lightgbm-2026-09-19-ef9430fb` |
| **Champion** | LightGBM with sigmoid calibration |
| **Frozen on** | 2026-09-19 (ticket T7) |
| **Code** | `src/prepaid_churn/training.py`, `evaluation.py`, `bundle.py`, `scoring.py` |
| **Configuration** | None separate: the choices are frozen into the bundle manifest |
| **Trained on** | One local CPU, about a minute end to end |
| **Card last updated** | 2026-09-21 |
| **Verified** | Fresh clone of `Ali_Branch`, 2026-09-21: the bundle version and every committed report reproduced unchanged |

## Intended use

The model estimates the probability that a prepaid subscriber makes no calls and uses no mobile data in the next calendar month.

It feeds three things, and nothing else:

- The **retention decision layer** (T11), which multiplies the probability by an assumed share of churners saved and an assumed 12-month value, then subtracts an estimated delivery cost.
  That arithmetic proposes an offer; it never sends one.
- The **employee copilot**, through `GET /portfolio/summary` (T15), which reads customers and dinar at risk by risk band and value tier.
- The **customer chatbot**, through `GET /subscribers/{id}/retention` (T15), which sees the approved offer and its reason and never the probability itself.

A person approves every retention action before it reaches a customer (decision 14).
The model produces an input to a constrained decision, not the decision.

## Out-of-scope use

This section matters more than the metrics.

- **Not for pricing, credit or any limit.** No output of this model may set a price, a discount, a credit line or an advance limit. T11 grants existing catalogue packages as bonuses and never computes a personalised price.
- **Not for a decision taken without a person.** Decision 14 requires a named reviewer on every proposal, and `released.csv` contains only approved rows.
- **Not evidence about operator subscribers.** The model is trained on the upGrad prepaid dataset from another market (decision 5). No figure in this card is a measurement of Libyan behaviour.
- **Not a commercial model.** The training data is for education only, so a model trained on it cannot be sold (decision 11). What can be sold is the pipeline, retrained on an operator's own export.
- **Not a cancellation predictor.** Churn here means observed inactivity, not a closed account. A subscriber who keeps a second SIM and stops using this one counts as churned, and one who keeps the line dormant but recharges does not.
- **Not for the already silent.** Subscribers with no calls and no data in the current month are not scored at all (decision 12); they receive the band `already_silent` and no probability.
- **No language model may sit in any path that sets an offer, a price or a limit** (decision 17). The chatbot and copilot read only.

## Training data

Source: upGrad "Telecom Churn Case Study", Kaggle hackathon version, `data/raw/train.csv`, committed to the repository on purpose (decision 9).

| | Value | Source |
|---|---|---|
| Customers in the raw file | 69,999 | `reports/profile.md` (T1) |
| Columns | 172, of which 55 are monthly base columns | `reports/profile.md` |
| Monthly columns with missing values | 41 of 55 | `reports/profile.md` |
| Months | 6, 7 and 8, plus a month 9 churn label | decision 5 |
| Engineered feature columns | 126, identical in every split | `reports/dataset_all.md` (T4) |

Split, from `reports/dataset_all.md`:

| Split | Window | Customers | Already silent, excluded | Rows used | Churn rate |
|---|---|---|---|---|---|
| train | A: months 6 and 7, label month 8 | 48,999 | 3,141 | 45,858 | 0.0465 |
| validation | A | 10,500 | 688 | 9,812 | 0.0461 |
| test | B: months 7 and 8, Kaggle's month 9 label | 10,500 | 823 | 9,677 | 0.0435 |

Customers are split 70/15/15, stratified by the window A label, so no customer appears in two splits.
The test split is also a **later window**, so the final evaluation is out of time as well as out of sample.

Churn is defined by usage, not by contract: a subscriber churns in month `m` when incoming calls, outgoing calls, 2G data and 3G data are all zero in month `m`.
The rule is in `src/prepaid_churn/labels.py`.

**No leakage by construction.** A feature may only use months up to and including the window's current month; month 9 never enters a feature.
Model selection, calibration and both thresholds were chosen on validation customers only.

Excluded from features: the label column, and the identifier columns.
No resampling, no reject inference and no synthetic rows were used.

## Metrics

Primary metric first.
Accuracy is not reported: at a 4.35% base rate a model that predicts "no churn" for everyone scores 95.65% and is useless.

Test results, window B, 9,677 unseen customers, from `reports/evaluation_all.md` (T7, run once on 2026-09-19):

| Metric | LightGBM | Logistic regression | Note |
|---|---|---|---|
| PR-AUC | **0.3477** | 0.2770 | primary |
| ROC-AUC | 0.8910 | 0.8696 | secondary |
| Log loss | 0.1261 | 0.1344 | |
| Brier score | 0.0338 | 0.0357 | calibration |
| Mean predicted probability | 0.0422 | 0.0447 | against an observed 0.0435 |

Two other models were tested and removed, because both were worse than LightGBM (decision 44):

- A Keras LSTM over the two monthly steps scored a test PR-AUC of 0.2326 against LightGBM's 0.3477, below the logistic regression too, and failed two of the four release checks.
  With two steps the change between months is one subtraction, which the engineered features already give LightGBM, so a sequence model has nothing to learn.
- A LightGBM trained on synthetic customers kept at most 45% of the real model's validation PR-AUC (Gaussian copula), and 15% with CTGAN.
  The generated customers did not keep the real patterns: a detector told them from real rows at ROC-AUC 1.000, and CTGAN's copy had 16.8% churners against 4.7%.

Contacting the riskiest customers, LightGBM, same source:

| Contact | Customers | Precision | Recall |
|---|---|---|---|
| top 5% | 484 | 0.3657 | 0.4204 |
| top 10% | 968 | 0.2676 | **0.6152** |
| top 20% | 1,935 | 0.1736 | 0.7981 |

The plain reading: contacting the riskiest tenth of the base reaches about 62% of the subscribers who go silent next month.

Risk bands on test:

| Band | Customers | Observed churn rate |
|---|---|---|
| high | 450 | 0.3844 |
| medium | 1,238 | 0.1195 |
| low | 7,989 | 0.0125 |

On the high-value slice (the top 30% by recharge amount) the model does better, not worse: ROC-AUC 0.9059 and PR-AUC 0.3825.

### Success thresholds

Four checks agreed with the instructor on 2026-09-19 (decision 13).
A model is fit for use only if it passes all four, and `churn bundle` refuses to package a champion that fails one.

| Check | What it measures | Value | Required | Passed |
|---|---|---|---|---|
| capture | Share of churners among the riskiest 10% | 0.6152 | at least 0.50 | yes |
| better_than_chance | PR-AUC divided by the churn rate | 7.9922 | at least 3.0 | yes |
| better_than_baseline | PR-AUC against logistic regression | 0.3477 | above 0.2770 | yes |
| calibration | Gap between mean predicted and observed rate | 0.0013 | at most 0.01 | yes |

Release gate: passed. Source: `reports/evaluation_all.md`.

How sure these numbers are: resampling the frozen test predictions 2,000 times (decision 35, `reports/uncertainty.md`) gives PR-AUC 0.3477 with a 95% interval of 0.3006 to 0.4000, and top-10% capture 0.6152 with 0.5725 to 0.6582.
LightGBM beat the baseline in all 2,000 paired resamples, and every check above still passes at the unfavourable end of its interval.
The intervals cover which customers landed in the test group; they do not cover training randomness or a different month or operator.

From the next model on, a fifth check applies: calibration inside the high and medium bands, where offers are made (decision 38).
It is set before that model is tested, and it does not apply to the current champion.

### Honest setup, and what selection costs

No deliberately naive variant was run, so no naive-versus-honest table is offered rather than a fabricated one.
What the reports do show is the price of choosing on validation.

| Slice | PR-AUC | Source |
|---|---|---|
| Validation, window A, uncalibrated | 0.4582 | `reports/training_all.md` |
| Test, window B, calibrated, scored once | 0.3477 | `reports/evaluation_all.md` |

The gap combines two things: the optimism of having selected the model and its thresholds on that validation set, and a genuinely different, later window.
The test number is the one to quote.

The traps that were avoided by design, each enforced in code and covered by tests:
random splits that put the same customer in train and test (customers are split, not rows), features drawn from the label month (window construction forbids it), thresholds tuned on test predictions (they are fixed on validation), and repeated test evaluation (the window is spent, and decision 18 forbids revisiting it).

## Calibration

Method: **sigmoid**, chosen by 5-fold cross-validated log loss on validation customers among none, sigmoid and isotonic.

| Model | none | sigmoid | isotonic |
|---|---|---|---|
| logistic_regression | 0.1342 | 0.1342 | 0.1361 |
| lightgbm | 0.1142 | 0.1142 | 0.1148 |

Calibration is mandatory here, because T11 multiplies the probability by money.
A probability consumed as a monetary expectation has to mean what it says.

On average it does: on test, the mean predicted probability is 0.0422 against an observed 0.0435, a gap of 0.0013.
Inside the range it does less well, and the average hides it because two errors cancel.
From the reliability table in `reports/evaluation_all.md`:

| Test customers | Predicted leavers | Actual leavers |
|---|---|---|
| Tenths 7 to 9 by predicted risk (1.1% to 10.9%), 2,903 customers | 98 | 134 |
| The riskiest tenth (10.9% and above), 968 customers | 283 | 259 |

The gap in tenths 7 to 9 is about 3.7 standard deviations, far beyond chance.
A smaller version already shows on the validation customers the calibrator was fitted on (121 leavers against 100 predicted), so part of it is the fixed shape of a sigmoid and part is the later month.

What it costs depends on the band, because T11 proposes offers only in the high and medium bands (counted from the frozen test predictions, decision 38):

| Band on test | Customers | Predicted leavers | Actual leavers | Actual against predicted |
|---|---|---|---|---|
| high | 450 | 199 | 173 | -13% |
| medium | 1,238 | 135 | 148 | +10% |
| low | 7,989 | 75 | 100 | +34% |

The ranking is not affected, so the riskiest customers are still found first.
Where money is spent, expected values are somewhat too high in the high band and too low in the medium band, which tilts a budget toward the high band; that error is small next to the assumed 5% share of churners saved.
The largest miss is in the low band, where T11 spends nothing: it holds 100 of the 421 leavers (24%), and the model expected 75.
None of this can be corrected with the test customers, which were scored once; decision 38 adds a check on the high and medium bands for the next model.

Thresholds, both fixed on validation and stored in the bundle manifest:

- **high**: 0.2511, the best-F1 threshold on validation customers.
- **medium**: 0.0461, the validation churn rate, so "medium" means above-average risk.

## Explainability

Every `high` or `medium` subscriber gets up to three reasons, each a short label with the customer's value, such as "Days since the last recharge, at the end of this month: 26", rather than `feature = value, shap = +0.14`.
A `low` subscriber gets one line instead, "Low risk: nothing stands out" (decision 40).
SHAP measures the push away from the average customer, so even a very safe customer has a few small upward pushes, and listing them would read as warning signs.

They are exact SHAP contributions, not an approximation: LightGBM computes them from its own trees through `pred_contrib`, so no background sample is needed and there is no sampling noise.
For the logistic regression baseline, each feature's share of the log-odds is its coefficient times its standardised value.
Only factors that raise the risk are reported.

The strongest features by share of total gain, from `reports/training_all.md`:

| Feature | Gain share |
|---|---|
| `cur_roam_og_mou` | 0.1288 |
| `trend_total_mou` | 0.0838 |
| `cur_days_since_last_rech` | 0.0523 |
| `cur_loc_ic_mou` | 0.0393 |
| `cur_roam_og_mou` and `cur_roam_ic_mou` together | 0.1658 |

Gain share says what the model leaned on, not why a particular subscriber was scored as they were; the per-subscriber reasons answer that.

## The human approval step

No offer reaches a customer without a named person approving it (decision 14).

- `churn decide` writes **proposals** only, each with a subscriber, an offer, a reason, an expected cost and an expected value.
- A reviewer approves or rejects with `churn approve --reviewer <name>`, or on the campaign screen of the demo app (T14).
- Only approved rows enter `released.csv`, which is what the chatbot reads through T15. Rejected and unreviewed rows never leave.
- Every decision is recorded in `review_log.jsonl` with the subscriber, the reviewer, the decision, the UTC time, an optional note and the campaign fingerprint.
- The JSON snapshot is authoritative. Editing a CSV cannot approve an offer, and the T15 service reads the snapshot rather than the derived file.

Reviewer names are an audit trail, not authentication. Access control between services is the API key boundary in T15 (decision 21).

## The operator view and its assumptions

The behaviour in this data is real but from another market; the money and the packages shown to a user are the operator's (decision 16).
Every assumption below is labelled, from `reports/operator_view.md`:

| What | Value | Status |
|---|---|---|
| Operator ARPU | 70 LYD per month | **assumption**, chosen by Ali on 2026-09-26 from the operator's bundle prices and Mordor Intelligence's Libya market figures (decision 42) |
| Reference monthly recharge | 537.17 source-currency units | measured on `train.csv` month 8 |
| Conversion rate | 1 source unit = 0.130313 LYD | derived from the two rows above |
| Recharge cards | 5, 10, 20, 40, 100 LYD | reported by Ali Marghem, 2026-09-18; on 2026-09-26 he confirmed that nothing below 5 LYD can be topped up |
| Bundle held | inferred from monthly and short pack purchases | **assumption**, the T18 rule |

Consequences worth stating next to any dinar figure:

- Every LYD amount inherits the 70 LYD ARPU assumption. Replace that one number in `data/operator/market.toml` and every amount moves with it.
- The anchor was 40 LYD until 2026-09-26; neither figure is a measured operator average, and decision 42 records the derivation and its limits.
- The viewed base has a mean monthly spend of 68.94 LYD, close to but not equal to the ARPU, because the rate is fixed on training customers rather than on the viewed batch.
- For 66.77% of active customers the nearest card to their usual top-up is the smallest one, 5 LYD.
- That card hides a limit of the one rate: it keeps monthly spend on the operator's scale, not the size of each top-up.
  For 49.9% of the active customers who recharged, the average top-up converts to under 5 LYD, which no customer of the operator can do, so a figure built on single top-ups, such as the emergency credit advice (T19), is not yet a Libyan one.
- The bundle a customer "holds" is inferred from purchase behaviour, never from an operator subscription record, because we have none.
- Only the money is converted, and the report measures what is not: 73.7% of active customers used no mobile data this month and the others a median 0.50 GB, while the 70 LYD anchor was built on 12 GB a month (decision 42).
- 422 customers (1.5%) spend more a month than the operator's dearest package, 400 LYD, with 16.3% of all spend and up to 5,709 LYD, so every LYD total leans on spenders the operator's catalogue does not reach.

The 12-month value used by T11 is a scenario, not a measured lifetime value (decision 19).
It assumes a constant monthly hazard and is reported in three variants, with the hazard multiplied by 1.5, 1.0 and 0.5.

Checked on 2026-09-26 on the validation customers, neither that assumption nor the assumption that nobody comes back holds (decision 41).
Risk moves back toward the average after a month: high-band customers who stayed active churned at 11.0% the next month, not the 43.2% predicted.
And 28.1% of customers silent in one month were active the next, while the scenario counts every silence as permanent.
Under constant risk, risk times value peaks near 20% risk, so the value of high-risk customers, and T11's reason to spend on them, is understated; ticket T23 replaces the scenario.

## Limitations

Stated plainly, because this is the section an evaluator should read hardest.

- **The data is not Libyan, and not the operator's.** It looks like an Indian operator's export: the columns carry "circle" regions and rupee amounts. Nothing here measures Libyan behaviour.
- **Provenance is undocumented.** The upGrad file gives no collection method, no sampling frame and no date range beyond four consecutive months.
- **One short history per customer.** Four months total, and only two of them feed features, so nothing seasonal or long-range can be learned.
- **Educational licence.** The Kaggle competition terms allow education only, so a model fitted on this data cannot be sold or deployed commercially (decision 11).
- **Only June to August exports can be scored.**
  The data contract names months by number and requires every date to fall in the month its column names, and the scorer always reads months 7 and 8.
  An operator's current base is refused unless its dates are rewritten into June to August, which is error-prone and shifts the recency features by the difference in month lengths.
  Ticket T22 moves this edge to match the inside of the pipeline, which already uses relative months (T4).
- **The test window is spent.** It was scored once, on 2026-09-19. No model, feature or threshold may change because of those numbers, and any future comparison must be against them rather than a re-scored test.
- **Churn is inactivity, so a dual-SIM subscriber who still receives calls but places none elsewhere looks retained.** The receiving-SIM hypothesis from `Ali_Branch` is testable only on real Libyan data.
- **One month of silence is not always churn.**
  Of 2,131 train customers who went silent in month 8, 561 (26%) were active again in month 9 by Kaggle's label (T6).
  The label counts temporary absence as churn, and an offer to a customer who would have come back anyway is spent for nothing.
- **The strongest signal is roaming, and it belongs to this market.**
  Customers roaming in the current month are 14% of the train customers but 52% of the churners, and the four roaming columns carry 19% of LightGBM's gain (T6).
  Without them, the same training recipe scores a validation PR-AUC of 0.401 instead of 0.458.
  Every customer here has the same home circle (`circle_id` 109), so roaming mostly means being away from that region, and roamers who went silent came back more often (35% against 17%).
  In Libya roaming would mostly mean being abroad, so this signal is likely to behave differently there, which is one more reason the model must be retrained on the operator's own data (decisions 11 and 16).
- **No causal claim.** The model ranks risk. It says nothing about whether contacting a subscriber changes their behaviour, which is what an offer needs. T11's "share of churners saved" is a declared assumption of 5% for every offer (decision 46), and it is not measured.
  With the same share for every offer, each customer gets the cheapest offer that fits them: in a 1,000 LYD campaign, 2,254 of the 3,643 offers are the 1 LYD morning pass and the rest the 0.5 LYD day pack.
  The campaign report's equal-spend comparison scores the targeted plan with the same assumed value it maximises, so it wins by construction and shows nothing about whether targeting works.
  The holdout, the same customers in every campaign (decision 43), is what can measure it.
- **No network-quality features.** Dropped calls and outages are not in this data. T20 defines the field contract for the network ML team to supply them later.
- **Age on network is a snapshot**, not a per-month value, so tenure carries the timing limitation recorded in T4.
- **Monthly recharge counters can overlap**, so the frequency measure is a count proxy rather than deduplicated transactions (T10).

## Ethical considerations

- **Protected attributes.** None are present in the data and none are used.
  The raw file has no gender, age, sex, religion, ethnicity, name or address column; the only person-adjacent fields are `aon`, which is age on network rather than age, and `circle_id`, an anonymised region code.
  `circle_id` is dropped before training and is not among the 126 feature columns, checked on 2026-09-21.
- **Fairness audit.** Not performed, and it cannot be performed on this data, because no protected attribute exists to audit against. On an operator's own export this becomes both possible and necessary before deployment.
- **Who is harmed if the model is wrong, and in which direction.** A false positive spends a small bonus on someone who was not leaving; the cost is the delivery cost of a catalogue package, capped per customer and per campaign. A false negative loses a subscriber who could have been kept. The asymmetry favours over-contacting, which is exactly why the guardrails, the budget and the human approval step exist: the model is not allowed to act on its own judgement of that trade-off.
- **What the customer is told.** The chatbot shows the offer and its reason. It is never shown the churn probability, the risk band, the value tier or the reviewer's name, so a subscriber cannot be told the operator thinks they are about to leave.
- **Identifiers.** Subscriber IDs are pseudonymous by contract. The T15 service refuses an identifier shaped like a Libyan mobile number, and `prepaid_churn.privacy.pseudonymize` is the supported way to hash numbers before export.

## Selection bias

The scored population is filtered by one explicit rule: only subscribers active in the current month are scored (decision 12).
Subscribers already silent are excluded rather than scored as certain churners, because the question "will they go silent next month" has no meaning for someone already silent.
They are reported in their own band, and their count is stated everywhere: 2,418 of the 30,000 in the unlabeled base, and 3,141, 688 and 823 in the three splits.

The optional high-value filter, which keeps the top 30% by average recharge, is **off by default**.
Nothing in the product uses it; it exists to compare with the upGrad case study's population (decision 36).
The headline metrics above are on the whole eligible population, not the flattering slice.
The high-value numbers are reported separately so the difference is visible rather than quietly baked in.

No other business rule filtered the training population, and no repayment or acceptance outcome is modelled, so the granted-only selection problem that affects credit models does not arise here.

## Maintenance

- **Retraining trigger.** There is none automated, deliberately. Retraining happens when an operator supplies its own export (decisions 11 and 16), which is also the only circumstance under which the model becomes commercially usable.
- **Drift monitoring.** None. No new data arrives, so there is nothing to drift against. On an operator's data this is the first thing to add.
- **What to check when the data changes.** Run `churn validate` against the new export: the input contract in `docs/data_contract.md` is generated from the code and is the single place an operator maps their fields to.
- **What to rebuild after a code change.** `churn bundle` refuses a bundle whose input-contract fingerprint or library versions do not match the running environment, so a stale bundle fails loudly rather than scoring quietly.
- **Reproducing everything.** The full pipeline in `README.md` rebuilds the model, the reports and the scores from a fresh clone in about a minute.
- **Contact.** Ali Marghem and Taha, Team Loop Gain.

## Sources

Every report is committed and regenerated by the command named beside it.
On 2026-09-26 a fresh clone of `Ali_Branch` ran the whole README rebuild, which regenerates every report in this table, and all of them came out byte for byte identical, with the same bundle, `lightgbm-2026-09-19-ef9430fb`.
The two contracts are checked against the code by the tests.
The earlier checks, on 2026-09-21 and 2026-09-22, regenerated only the pipeline reports; the T1 profile and the readiness decisions report were first regenerated on 2026-09-26.
A few figures come from one-off checks instead of a report: the roaming and come-back numbers (T6, 2026-09-25) and the calibration counts by band (decision 38, 2026-09-26).
They are dated where they appear, and no command regenerates them.

| File | Contents | Produced by |
|---|---|---|
| `reports/profile.md` | Raw data profile: rows, columns, missing values | `churn profile` |
| `reports/dataset_all.md` | Splits, windows, eligible rows, churn rates | `churn build-dataset` |
| `reports/training_all.md` | Validation metrics and feature gain shares | `churn train` |
| `reports/evaluation_all.md` | Frozen choices, test metrics, success thresholds | `churn evaluate` |
| `reports/uncertainty.md` | 95% intervals on the frozen test metrics; changes nothing | `churn uncertainty` |
| `reports/operator_view.md` | Money and packages in the operator's terms, with statuses | `churn operator-view` |
| `reports/tiers.md` | Value tiers, cutoffs and the clustering comparison | `churn fit-tiers` |
| `reports/decisions.md` | Retention proposals with every cost and effect assumption | `churn decide` |
| `reports/emergency_credit.md` | Advised emergency credit limits; uses no model | `churn advance` |
| `docs/data_contract.md` | What an operator export must contain | `churn contract` |
| `docs/output_contract.md` | The per-subscriber output contract | `churn output-contract` |
| `docs/decisions.md` | Why each decision was made, with its date | written by hand |
