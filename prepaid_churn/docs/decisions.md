# Decision log

Why the churn module looks the way it does.
Newest decisions go at the bottom.
Every entry says what was decided, why, and what it rules out.

## 1. We do not build on Ahmed's `customer_churn_prediction/` module

Date: 2026-09-13.

Taha asked for an independent audit of the existing churn module before reusing it.
The audit found problems serious enough to start fresh in `prepaid_churn/`:

- **Label leak from dropping "Joined" customers.**
  The Maven dataset has 4,720 Stayed, 1,869 Churned and 454 Joined customers.
  Joined customers have tenure 1 to 3 months, and the smallest Stayed tenure is 4.
  Dropping Joined therefore makes every remaining customer with tenure of 3 months or less a churner (597 customers, 32% of all churners).
  Tenure alone then separates a third of the churners perfectly, which inflates ROC-AUC.
- **Offers are a function of tenure, so "migrate to Offer A" is meaningless.**
  Offer A covers tenure 66 to 72 months, B 40 to 65, C 24 to 39, D 10 to 23 and E 1 to 10.
  Offer E's "67.6% churn" is new customers churning, plus the Joined leak (with Joined included it is 52.9%).
  Within the same tenure band the offer differences mostly disappear.
- **The headline "+$917,265.70" is not real.**
  $718,001.87 of it (78%) comes from 1,869 customers who had already churned.
  981 of the 1,210 VIP_SAVE customers had already churned.
  The scores are in-sample: 80% of the scored customers were in the training set.
- **Probabilities are not calibrated but are used as money.**
  `scale_pos_weight=2.2` distorts them: on the held-out test set, predicted 0.56 means 0.29 actual churn, and predicted 0.75 means 0.55.
- **Evaluation used the test set for decisions.**
  The champion was picked by test ROC-AUC (0.9280 vs 0.9278, within noise) and the 0.63 threshold was tuned on the test set.
  The discount engine then ignores that threshold and hardcodes 0.60 and 0.35.
- Smaller issues: dead and contradictory `DISCOUNT_TIERS` config, 120 negative monthly charges left unhandled, gender and age feeding discount decisions, report numbers that no code produces (the 75% acceptance rate and the strategy comparison), no tests, and about 100 MB of datasets committed to git.
- The Maven and IBM Telco data describe a fictional company (IBM calls it fictional), and it is a postpaid, single-snapshot dataset.

Ahmed's folder stays untouched on this branch.
If `prepaid_churn/` works, the team deletes the old folder later.

## 2. No two-tower architecture

Date: 2026-09-13.

Two-tower (dual encoder) models were built for retrieval: matching one user against millions of items fast (YouTube, Pinterest).
Churn scoring has no item catalog, so the architecture solves no problem here.
No published work shows it beating gradient boosting for churn classification.
It could only fit customer-to-offer matching with a large offer catalog and logged offer exposures, and we have neither.

## 3. LightGBM plus a logistic regression baseline

Date: 2026-09-13.

Research on tabular benchmarks (Grinsztajn 2022, McElfresh 2023, TabArena, TALENT) says:

- Tuned gradient boosting stays the practical default for tabular data with CPU serving, calibration and explanations.
- Tabular foundation models (TabPFN and similar) can score higher, but newer versions need a commercial license for production use and a GPU.
- Deep tabular models (RealMLP, TabM) need heavy tuning and GPUs to win.
- CatBoost's main advantage is categorical features; our data is almost entirely numeric, so we use LightGBM.

Logistic regression stays as the honest baseline that catches leakage and overfitting.

## 4. Retention offers need a holdout group, not just a risk score

Date: 2026-09-13.

Ascarza (2018, Journal of Marketing Research) showed with randomized field experiments that the customers most likely to churn are often not the ones an offer can save.
Targeting by risk left much of the gain on the table, and in one study it increased churn.
So:

- Offer decisions use an expected-value rule with explicit, configurable assumptions, never invented acceptance rates presented as facts.
- Every campaign keeps a random holdout group, so a real deployment can later measure which customers an offer actually keeps (uplift).
- We do not claim causal effects from historical offer data, because historical offers were assigned by rules (for example by tenure).

## 5. Dataset: upGrad prepaid telecom data

Date: 2026-09-14.

Chosen: the upGrad "Telecom Churn Case Study" data, Kaggle hackathon version, `train.csv` (69,999 customers).

Why:
- It is **prepaid**, like the Libyan market (Libyana and Al-Madar), and churn means inactivity, not a cancelled contract.
- It is a **monthly panel** (months 6, 7, 8 plus a month 9 label), so features can come from months before the label month.
- It has real versions of the signals a Libyan operator would use: on-net and off-net minutes, incoming and outgoing calls, recharge count, amount and date, night packs, social-network packs, roaming, and age on network.

Rejected:
- IBM Telco and Maven: fictional, postpaid, one snapshot.
- Cell2Cell and the 100k Teradata data: real but US postpaid from around 2000, with churn deliberately enriched to about 29% and 50%.
- Iranian UCI churn: only 3,150 rows and a mix of pay-as-you-go and contract customers.
- KKBox: real and time-stamped but music streaming, not telecom.

Known limits, stated in the model card:
- Provenance is undocumented (it looks like an Indian operator: "circle" regions and rupee amounts).
- Only four months, so there is one short history per customer.
- Educational use only, under the Kaggle competition rules (see decision 9 for how the files are shared).
- Kaggle's `test.csv` has no labels and is not used for evaluation.

## 6. Split design: customer split plus a later-month test

Date: 2026-09-14.

Customers are split 70/15/15 into train, validation and test.
Train and validation use window A (features from months 6 and 7, label month 8, which we compute).
Test uses window B (features from months 7 and 8, Kaggle's month 9 label) on test customers only.
So the final score measures unseen customers **and** a later month, which is how the model would run in production.
A plain random split would never test on a future month.

## 7. The CVM Suite proposal shapes our module, with the synthetic parts cut

Date: 2026-09-18.

Taha's friend proposed an "AI CVM Suite" with seven modules.
Decided with Taha: it only shapes our churn module; the team keeps antenna placement and the chatbot.

Kept:
- Inactivity churn, calibrated probabilities and honest metrics.
- Prepaid value tiers (recency, frequency, monetary value, tenure).
- Offer decisions with guardrails: bonus data before discounts, a budget cap, no offers to safe high-value customers, a random holdout, and a decision log with reasons.

Cut:
- Generating a "Libyan" population with CTGAN and hand-written churn labels.
  The source datasets share no customers, so a GAN cannot learn one joint profile from them.
  The Libyan fields would come from our own rules, so every metric would measure our own formula.
- Smart Advance (airtime credit), the network AutoEncoder and Cox survival: no real data exists for them.
  They stay as future work that needs operator data.
- Arabic complaint classification and the LangChain copilot: they belong to the team's chatbot module.
- MLflow, Evidently, a DuckDB feature store, a five-container Docker Compose, Optuna, locust and Oracle Cloud.
  Markdown and JSON reports, `uv`, `ruff` and `pytest` are enough at this size.

Fact-check notes on the proposal:
- The Iranian dataset is not purely prepaid (its `Tariff Plan` column is pay-as-you-go vs contractual).
- Cell2Cell has no daily sequences, so an LSTM on it is impossible without inventing sequences.
- The upGrad data already contains real versions of most fields the proposal planned to generate.

## 8. Syllabus chapters are covered by small experiments on real data

Date: 2026-09-18.

SIC grades syllabus coverage, so our module covers the chapters that fit churn, each as a small, honest experiment:

| Chapter | Where |
|---|---|
| Ch 5 supervised learning | T6 and T7: logistic regression, LightGBM, calibration |
| Ch 6 unsupervised learning | T10: K-Means, PCA plot, dendrogram on value features |
| Ch 8 deep learning, Ch 9 RNN | T12: Keras LSTM vs LightGBM on the monthly panel |
| Ch 9 GAN | T13: CTGAN "privacy-safe synthetic copy", train on synthetic and test on real |

Chapters 7 and 10 (NLP and LLMs) belong to the chatbot module.
Experiments use a separate `experiments` dependency group, so the core package stays small.
SDV and CTGAN use the Business Source License, which allows non-production use such as this experiment.

## 9. The raw data is committed to the private repo

Date: 2026-09-19.

Taha decided to commit `train.csv`, `test.csv` and `data_dictionary.csv` (about 72 MB) in `data/raw/`.

Why: teammates can clone the repo and run everything immediately, without each creating a Kaggle account.

Trade-offs Taha accepted:
- The Kaggle competition rules say data may not be shared privately outside a Kaggle team, and the SIC team is not a Kaggle team.
- Files in git history stay there even if deleted later.

Consequences:
- The repo must stay private, and the data must never be copied anywhere public.
- `data/processed/` and `artifacts/` stay git-ignored; they are rebuilt by the pipeline.

## 10. Integration with the team's other services

Date: 2026-09-19.

The team's SIC action plan combines this module with a customer chatbot (offers and nearby service points) and an employee copilot (questions about network, planning and, "where authorized", customer intelligence).
So the churn module is built as a service with two fixed contracts and simple integration points first:

- **Input contract** (`docs/data_contract.md`, T2): what an operator export must contain.
  An operator integrates by producing a file that passes `churn validate`.
- **Output contract** (T8, extended by T11): one row per subscriber with subscriber ID, calibrated churn probability, risk band, top three reasons in plain language, value tier, recommended offer and its reason, model version and scoring time.
- **For the customer chatbot:** it shows the recommended offer and its reason, never the raw churn probability, and only for the subscriber it is talking to.
- **For the employee copilot:** portfolio summaries (customers and revenue at risk by risk band and value tier) plus the model's test metrics.
- **Integration points, simplest first:** the `score` function and the versioned output file (T8).
  A small HTTP service (T15) is built only when a teammate's service needs to call us over the network.

Both contracts are generated from code and checked by tests, so the documentation cannot drift from what the code does.

## 11. Real Libyan market data and commercial use

Date: 2026-09-19.

Taha and the team want the product as close to the real market as possible, and may try to sell it.

Findings:
- Nothing in the repo contains real Libyana or Al-Madar packages or prices; only tower locations and operator codes (in the antenna module).
- Al-Madar publishes its data packages on its website; Libyana's site blocks automated requests but works in a normal browser.
  T16 builds a real package catalogue from these official sources, with a collection date on every row.
- The Orange Belgium Churn-Uplift dataset in the action plan is real: 11,896 customers of a real phone retention campaign with a random control group.
  It is postpaid, its features are anonymized, and its license is non-commercial (CC BY-NC-ND 4.0), so it serves the T17 experiment only.

Consequence for selling:
- Both training datasets are for education or non-commercial use only, so models trained on them cannot be sold.
- What can be sold is the pipeline: the input contract, cleaning, features, training, calibration and decision logic, retrained on the operator's own export.
- The data contract is therefore written so that a Libyan operator can map its own data to it (see "Adapting a Libyan export" in `docs/data_contract.md`).
