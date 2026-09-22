# Models and data of the prepaid customer module

Every model this module contains and every dataset it reads, in one place.
Only the prepaid customer module is listed; the GIS, network ML, chatbot and copilot parts of the platform are not.

Each figure names the file it comes from, because the employee copilot indexes these documents (decision 17).
The numbers are copied from committed reports that a fresh clone regenerates byte for byte.

Last checked: 2026-09-22.

## Models

### In production

One model is deployed. It is packaged as bundle `lightgbm-2026-09-19-ef9430fb` and frozen on 2026-09-19 (T7).

| Model | Role | Code |
|---|---|---|
| LightGBM (`LGBMClassifier`) | Champion. Predicts the probability that a subscriber makes no calls and uses no mobile data next month. | `training.py` |
| Logistic regression (`log1p` scaling, then `StandardScaler`, then `LogisticRegression`) | Baseline the champion has to beat before it may be bundled. | `training.py` |
| Sigmoid calibrator (Platt scaling) | Chosen over `none` and `isotonic` by 5-fold cross-validated log loss on validation customers. | `evaluation.py` |

Calibration is not optional here.
T11 multiplies the probability by money, so a probability consumed as a monetary expectation has to mean what it says.
On the frozen test the mean predicted rate is 0.0422 against an observed 0.0435, a gap of 0.0013 (`reports/evaluation_all.md`).

Test results on the frozen window, from `reports/evaluation_all.md`:

| Metric | LightGBM | Logistic regression |
|---|---|---|
| PR-AUC (primary) | 0.3477 | 0.2770 |
| ROC-AUC | 0.8910 | 0.8696 |
| Log loss | 0.1261 | 0.1344 |
| Brier score | 0.0338 | 0.0357 |

Accuracy is deliberately not reported.
At a 4.35% churn rate a model that predicts "no churn" for everyone scores 95.65% and is useless.

### Unsupervised, for comparison only

These never score a customer and never enter a decision.
They exist to check whether the five business value tiers correspond to anything the data separates on its own (T10).

| Model | Role | Result |
|---|---|---|
| K-Means | Compared against the five value tiers on training customers only. | Weak: best silhouette 0.2766 at k=2 (`reports/tiers.md`). |
| Ward hierarchical linkage | Dendrogram on a 300-row sample, for the same comparison. | Shows no clean separation. |
| PCA | Two-dimensional plot only. | Never a model input, because it destroys per-customer explanations. |

The conclusion recorded in T10 is that the five value tiers remain a reporting convention rather than natural customer segments.

### Experiments, none deployed

All three produced negative results, and all three are kept as they came out.

| Model | Ticket | Result |
|---|---|---|
| Keras LSTM, one layer with dropout, on the torch backend | T12 | Loses. Test PR-AUC 0.2326 against LightGBM's 0.3477, and it fails two of the four release checks (`reports/sequence_benchmark.md`). |
| CTGAN and Gaussian Copula | T13 | A synthetic copy is a demo, not a way to share data. The best copy keeps 45% of the real model's PR-AUC, and both copies are told from real rows at a detection ROC-AUC of 1.000 (`reports/synthetic.md`). |
| Two-model uplift, two LightGBM classifiers over treated and control arms | T17 | Targeting by uplift and targeting by risk are not the same ranking. On Criteo the risk ranking scores worse than random (`reports/uplift.md`). |

The LSTM losing is the expected answer, not a failure.
A window carries two monthly steps, which is far too short a sequence for a recurrent model to beat gradient boosting on tabular features.

### No model at all

Two parts of the module are rule-based by design and contain no learned component.

- T11 retention decisions: catalogue bonuses chosen by expected value under stated assumptions, with guardrails, a budget and a random holdout.
- T19 emergency credit advice: one affordability rule over observed recharge behaviour. There is no repayment model and there will not be one until an operator supplies repayment history (decision 15).

## Data

### The training dataset

The upGrad "Telecom Churn Case Study" prepaid data, Kaggle hackathon version, committed at `data/raw/train.csv` (decision 9).

- 69,999 subscribers, about 48 MB.
- Months 6, 7 and 8 of behaviour, plus a month 9 churn label.
- 172 columns, of which 55 are monthly base columns (`reports/profile.md`).

Subscribers are split 70/15/15 **by customer**, not by row, stratified by the window A label, so no subscriber appears in two splits.

| Split | Window | Customers | Already silent, excluded | Rows used | Churn rate |
|---|---|---|---|---|---|
| train | A: months 6 and 7, label month 8 | 48,999 | 3,141 | 45,858 | 0.0465 |
| validation | A | 10,500 | 688 | 9,812 | 0.0461 |
| test | B: months 7 and 8, Kaggle's month 9 label | 10,500 | 823 | 9,677 | 0.0435 |

Source: `reports/dataset_all.md`.
Every split carries the same 126 engineered feature columns.

Two properties matter more than the sizes.

The test split is a **later window as well as unseen customers**, so the final evaluation is out of sample and out of time at once.
It was scored **once**, on 2026-09-19, and is spent: no model, feature or threshold may change because of those numbers, and a later comparison must be made against them rather than against a re-scored test.

There is **no leakage by construction**.
A feature may only use months up to and including the window's current month, and month 9 never enters a feature.
Model selection, calibration and both risk thresholds were chosen on validation customers only.

### The scoring base

Kaggle's unlabelled file, committed at `data/raw/test.csv`.

- 30,000 subscribers, about 21 MB.
- It has no labels, so it is **never used for evaluation**.
- It stands in for "this month's live base" for `churn score`, `churn tiers`, `churn decide` and `churn advance`.

Scored with the real bundle it gives 1,209 high risk, 3,594 medium, 22,779 low and 2,418 already silent.

### Supporting files, not training data

| File | What it holds |
|---|---|
| `data/almadar/offers.csv` | The 37 Almadar packages still sold, in 12 families. |
| `data/almadar/excluded.csv` | The 20 Mix packages the operator retired, each with a reason and a date (decision 31). |
| `data/almadar/market.toml` | Tariffs, recharge cards, the two emergency credit products and the 40 LYD ARPU assumption, each with a status. |
| `data/almadar/source/` | The operator's own material, byte for byte, as evidence for the two files above. |

### External datasets, experiments only

These are downloaded on demand into `data/external/`, which is git-ignored.
Neither is ours to redistribute, so unlike the Kaggle data they are never committed.

| Dataset | Ticket | Size and role |
|---|---|---|
| Orange Belgium, OpenML 45580 | T17 | 11,896 customers, a real telecom retention campaign with a random control arm. Too small to answer the question, and the report says so rather than picking a winner. |
| Criteo uplift v2.1, 10% sample | T17 | About 1.4 million rows from a real randomised trial. Advertising, not telecom. |
| Synthetic copies | T13 | 6,000 rows generated from window A training customers only. No synthetic row has ever trained a delivered model. |

## What this means for selling the work

Every dataset that trains anything here is licensed for education only.
A model fitted on them cannot be sold or deployed commercially (decision 11).

What can be sold is the pipeline: the input contract, cleaning, features, training, calibration and the decision layer, retrained on an operator's own export.
The input contract in `docs/data_contract.md` is written so a Libyan operator can map its own fields to it.

## Where these figures come from

| Report | Contents | Regenerated by |
|---|---|---|
| `reports/profile.md` | Raw data profile | `churn profile` |
| `reports/dataset_all.md` | Splits, windows, rows, churn rates | `churn build-dataset` |
| `reports/training_all.md` | Validation metrics and feature gains | `churn train` |
| `reports/evaluation_all.md` | Frozen choices, test metrics, success thresholds | `churn evaluate` |
| `reports/tiers.md` | Value tiers and the clustering comparison | `churn fit-tiers` |
| `reports/sequence_benchmark.md` | The LSTM against the champion | `churn sequence-benchmark` |
| `reports/synthetic.md` | What a synthetic copy is worth | `uv run --script experiments/synthetic.py` |
| `reports/uplift.md` | Risk targeting against uplift targeting | `uv run --script experiments/uplift.py` |

See [model_card.md](model_card.md) for what the champion may and may not be used for, and [decisions.md](decisions.md) for why each choice was made.
