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

## 12. The model only scores customers who are still active

Date: 2026-09-19.

Only customers with calls or data in the current month are trained on, validated and scored.

Why (T1 numbers):
- 59.9% of month 9 churners were already silent in month 8, and silent customers churn at 77.9%.
- Predicting them is trivial and useless: they have already left in practice, and no retention offer reaches a silent line.
- Keeping them would inflate every metric, because the model would mostly learn "silent last month means silent next month".

Consequences:
- The churn rate among eligible customers is about 4.4% to 4.7% (T4), so the problem is harder and the metrics are honest.
- Our metrics will look lower than published results on this dataset, which usually include the silent customers.
- Silent customers are handled by a rule instead of the model: T8 gives them the risk band `already_silent`.

## 13. Success thresholds

Date: 2026-09-19.

The instructor's review of the SIC action plan asked for "success thresholds" per task.
A churn model is fit for use only if, on an out-of-time test (a later month, unseen customers, active customers only), it passes all four:

1. **Capture:** the riskiest 10% of customers contain at least 50% of the churners.
   This is the business question: a retention team can only call a small share of customers, so most churners must be in that share.
2. **Better than chance:** PR-AUC is at least 3 times the churn rate (random ranking scores about the churn rate).
3. **Better than the baseline:** the champion's PR-AUC is higher than the logistic regression baseline's on the same test, otherwise the simpler model wins.
4. **Calibration:** the mean predicted churn rate is within 1 percentage point of the observed rate, because T11 turns probabilities into money.

Why these levels: they are minimums a retention team would accept, not numbers tuned to our result.

Honesty note: the thresholds were written after the T7 test run (the current champion passes all four: 61.5%, 8.0 times, 0.348 vs 0.277, 0.13 points).
So that pass is a check, not a pre-registered result.
From now on the thresholds gate every new model before use (T8).

## 14. A person approves every retention action

Date: 2026-09-19.

The instructor asked for "a human approval step for retention actions", and the copilot must not make customer decisions.
So:

- The decision layer (T11) only **proposes** offers, each with its reason, expected cost and expected value.
- A named reviewer approves or rejects proposals before anything is sent or shown to a customer by the chatbot.
- Only approved proposals are released; rejected and unreviewed ones never leave the module.
- Every review is logged with the reviewer, time, decision and an optional note, so each action can be traced.
- The copilot only reads summaries; it has no path to approve, create or send offers.

## 15. One module from two efforts: this branch plus Ali's `Ali_Branch`

Date: 2026-09-19.

Ali Marghem built the "AI CVM Suite" in parallel on the remote branch `Ali_Branch` (commit `06890f6`).
Taha asked to take the best of both into one module on `tahaDev`.
The full review and every ported piece are logged in [ali_branch_merge.md](ali_branch_merge.md).

What the review found:
- `Ali_Branch` shares no history with `main` or `tahaDev`: it is a separate repository pushed as a branch, with its own files at the repo root.
- Its churn labels come from a formula Ali wrote (`src/cvm/synthesis/hazard.py`), applied to 100,000 generated subscribers built from Cell2Cell (US postpaid, around 2000).
  So its churn, value and uplift results measure that formula, as Ali's own docs say.
- It also holds real, valuable work: Almadar Aljadid's published packages, prices, recharge cards and emergency credit rules, a careful offer engine design, an HTTP contract for the chatbot and copilot with grounding rules for LLMs, and a list of serving bugs found the hard way.

Decided:
- This module stays the base: real data, `uv`, and the frozen T7 champion.
- `Ali_Branch` is **not** merged with git.
  Its history is unrelated and its root-level files would collide with the team repo.
  Pieces are ported by hand, each one logged in `docs/ali_branch_merge.md` with its source path, and the commits credit Ali as co-author.
- `Ali_Branch` stays on GitHub untouched, as the record of his work.

Taken (the ticket that uses each piece is in brackets):
- Almadar catalogue, tariffs, recharge cards and emergency credit rules (T16).
- Mapping money onto Almadar's scale (T18).
- Offer engine design: the real catalogue as the action space, "no offer" as a real option, the guardrails including the cannibalisation guard keyed on the bundle a customer holds, the equal-spend comparison, the holdout and the decision log (T11).
- Serving lessons: everything a scoring run needs travels inside the bundle, pinned library versions, a smoke prediction at load time, and one-row batches as a test case (T8).
- The API and screen designs, and the grounding rules for LLM consumers (T14, T15, T20).
- Prepaid value segmentation (T10), two-model uplift with Qini and the Criteo validation (T17), the emergency credit rules (T19), the synthesis engine and its quality gate (T13), and the model card template (T9).

Not taken, and why:
- The generated population and its formula labels, and every result measured on them: decision 7, the metrics would measure the formula.
- The repayment model for emergency credit: no real repayment data exists.
- Cox and random survival forests: our data is monthly, so there is no time-to-event to model.
- DuckDB feature store, MLflow, Docker, conda and the eight-model benchmark: decision 7, not needed at this size.
- Cell2Cell, IBM Telco, UCI Iranian, Hillstrom and Online Retail as data sources: decisions 5 and 7.

Conflicts between the two efforts, and how they are settled:
- Syllabus coverage: `Ali_Branch` removed chapter tracking; it stays here, because SIC grades it (decision 8).
- Data in git: `Ali_Branch` never commits data; the raw Kaggle files stay committed here (decision 9).
- Churn definition: `Ali_Branch` uses "30 days without a top-up"; we keep the usage-based rule, because the only real label (Kaggle's month 9) uses it.

## 16. Almadar Aljadid is the operator, and real customers are shown in Almadar terms

Date: 2026-09-19.

Almadar Aljadid (MCC-MNC 606-01) is the only Libyan operator with real, confirmed data in the project: its published packages, prices, recharge cards and emergency credit rules, collected by Ali on 2026-09-18.
Libyana has none yet, so this updates decision 11: the module targets Almadar, and Libyana can be added later as more rows in the same catalogue.

How the two datasets meet:
- The churn model keeps training on the real upGrad customers in their original units.
  The T7 champion stays frozen.
- The business layer (value, offers, emergency credit, app) shows each real customer in Almadar terms (T18): money in LYD, the Almadar bundle they would hold, and their usual recharge card.
- The conversion is one documented scale anchored on stated assumptions, kept in one file with a status per value (confirmed, assumption or estimate).

What the report must say: the behaviour comes from a real prepaid operator in another market; the prices, packages and money are Almadar's; real use needs retraining on Almadar's own export (decision 11).

## 17. The customer MVP comes first, built to plug into the team platform

Date: 2026-09-19.

The instructor's review of the action plan asked to:
- narrow the MVP to one measurable customer use case, so the three weeks allow credible integration and testing;
- protect customer data through de-identification, access control and a human approval step for retention actions;
- use the employee copilot only as retrieval-grounded Q&A over approved model outputs and documentation, with citations and refusal when evidence is missing, never making network or customer decisions.

The team's final goal is one platform: GIS planning, network ML, this customer module, a customer chatbot and an employee copilot.
In the action plan, Taha owns the chatbot, the copilot and the integration, and Ali owns customer intelligence and the chatbot.

Our MVP use case: "Which active prepaid customers are likely to stop using their line next month, and which approved Almadar offer should each one get?"
The MVP path is T16, T8, T18, T10, T11, T15, T20, T14 and T9.
T12, T13, T17 and T19 come after the MVP works end to end.

How the module links to each part of the platform (extends decision 10):
- **Customer chatbot:** reads the Almadar catalogue (T16) and, for the one subscriber it is talking to, the approved offer and its reason (T15).
  It never sees a churn probability.
- **Employee copilot:** reads portfolio summaries (T15) and indexes this module's documents (model card, contracts, decisions) for retrieval with citations.
  It gets no subscriber rows and has no way to create, change or approve an offer.
- **Network ML:** a future input.
  Once operator data exists, per-subscriber network quality (dropped calls, outage hours) can become churn features; the field contract is written in T20, and nothing is built before then.
- **GIS planning:** no direct data link, because the churn data has no location.
  The copilot combines the two only at the answer level.

Rules that follow from the review:
- **No LLM in any path that sets an offer, a price or a credit limit.**
  LLM components read and explain API outputs; Ali's grounding rules (never invent a number, cite the field, refuse rather than guess) are part of the contract (T20).
- **De-identification:** subscriber IDs are pseudonymous.
  An operator hashes phone numbers with a secret salt before export, the module never receives a phone number, and the API rejects IDs shaped like one (T15).
- **Access control:** the chatbot and the copilot use separate API keys, each limited to its own endpoints (T15).
- **Human approval:** unchanged from decision 14.

## 18. Review delivery on Ali_Branch, with the frozen modelling choices preserved

Date: 2026-09-20.

Ali requested a comprehensive review of `tahaDev`, with all commits and the push going only to `Ali_Branch`.
After being told that the branches have unrelated histories, he explicitly chose to replace the tracked contents of `Ali_Branch` with the reviewed `tahaDev` project.
This supersedes decision 15's instruction to leave that destination branch untouched for this delivery.
The old CVM work remains in Git history; it is not ported into this tree.
The source reviewed is `tahaDev` commit `bfb28ab`.

T21 records this review; [../../CODE_REVIEW.md](../../CODE_REVIEW.md) records the findings and validation.
The changes preserve the model families, features, split policy, calibration selection, risk thresholds and business assumptions.
No model choice was made from test outcomes and no real-data test evaluation was repeated.
The stricter export checks preserve all model features for valid existing exports.
The generated input contract changes its fingerprint, so an older bundle must be rebuilt with `churn bundle` from its existing champion and gate, without running `churn evaluate` again.
New bundle manifests also carry a model-file checksum and are checked against the stored feature order and thresholds.

## 19. Frozen value tiers and explicit revenue scenarios before operator data

Date: 2026-09-20.

Ali asked to continue with improvements that do not depend on an operator export, starting with T10.
We adapt the five dimensions and clustering comparison from Ali's original prepaid RFM work, using only fields present in the real upGrad data.
We do not infer recharge regularity, lifetime spend, continuity, SMS or credit behaviour that this export cannot establish.
Recency is the more recent of airtime and data recharges; frequency is the average monthly sum of their separately recorded counts.
The count is a proxy because the monthly aggregates cannot deduplicate overlapping events.
Monetary uses the existing T18 recharge definition and LYD conversion; tenure retains T4's extraction-snapshot limitation.
Engagement counts use of voice, data, packs and roaming over the two feature months.

Dimension quintiles and the equal-weight composite tier cutoffs are fitted once on the active training customers in window A.
This is unsupervised value preprocessing, independent of T7's validation-only model selection and risk thresholds.
Recency is negated before ranking so a recent recharge scores higher.
Ties go to the lower interval and never split by customer order; proportions may differ from 20% and some tiers can be empty.
A constant training dimension carries no ranking information and stays at neutral score 3.
Missing activity blocks are cleaned under the existing contract; other missing or invalid measures fail explicitly.
The cutoffs and monetary rate are saved together with a content-derived version, so serving never learns from its batch or a changed market file.

The 12-month scenario sums survival at the next 12 month ends: `sum((1-p)^m, m=1..12)`.
It assumes constant monthly hazard p and spend, no reactivation, no growth, no discounting and no margin adjustment.
The one-month usage-inactivity probability has not been validated as a 12-month revenue hazard.
Multiplying it by 1.5 and 0.5 (clipped to [0,1]) gives low/high value sensitivities, not confidence intervals.
The outputs are revenue scenarios, never validated CLV, profit or causal offer savings; T11 must preserve that distinction.
Already-silent customers have no probability and no scenario amount, even when they still recharge.

`churn fit-tiers` reads training parquet only and writes the artifact and clustering comparison.
`churn tiers` applies it and scores the same export with the existing gated churn bundle, avoiding stale risk joins.
`--tiers-only` explicitly omits churn scoring, leaves scenario values empty and marks active customers `risk_unavailable`.
This lets a fresh checkout use T10 without rebuilding or reevaluating the frozen churn model.

Clusters remain an exploratory check, separate from serving tiers and retention decisions.
K-Means fits scaled dimension scores on training customers only, searches k=2..8 with seed 42 and 10 starts, and selects by silhouette on one fixed sample of at most 2,000.
PCA plots at most 2,000 rows and Ward linkage at most 300; no subscriber identifiers enter the committed plots.
The report states that the tiers are a reporting convention and that discretized scores can themselves create apparent clusters.
SciPy is now declared directly because the dendrogram uses it; its already-locked version and all other package versions remain unchanged.
The frozen churn model, feature definitions, evaluation reports and spent test window are untouched.

## 20. Retention proposals with explicit assumptions and a separate review step

Date: 2026-09-20.

Ali requested T11 after completing the frozen value layer, without waiting for operator data.
The decision engine uses T8 risk, T10 value and T18's inferred held bundle from the same raw export.
It does not fit models, join stale risk CSVs, invent probabilities or reevaluate the spent test window.
The catalogue remains the action space, plus an explicit `NO_OFFER` outcome.
All interventions are bonus grants of existing products, not personalized price discounts.

All T11 policy and delivery-cost assumptions are in `data/almadar/retention.toml`.
Defaults: 1,000 LYD campaign budget, 15% of the base T10 value as the per-customer campaign cap, approximately 10% holdout and seed 42.
Delivery estimates start from T16: 25% of catalogue price for metered products and 35% for unlimited products.
The assumed share of churners saved is 5% for ordinary bonuses and 10% for the preferred morning product, `SABAH_1`.
That off-peak advantage is a planning assumption, not a measured response or network-cost finding.
Changing the assumption can change the winning offer; no effect is learned from the available churn labels.
The report lists every parameter and every product's estimated cost and assumed effect beside the results.
The net-value formula is `p * share_saved * value_12m_base_lyd - delivery_cost`.
It inherits T10's unvalidated 12-month revenue assumptions and is neither audited profit nor causal uplift.

Guardrails apply before allocation:
- Already-silent, unscored, low-risk and held-out subscribers get no proposal.
- A bonus must include a service the subscriber used in the two feature months.
- 5G/network-specific and shared-family products are excluded because coverage, device and membership eligibility are unavailable.
- For customers mapped to monthly bundles above `MO_20` (35 LYD), every cheaper unlimited bonus is blocked, regardless of risk.
- Offer delivery cost must fit the per-customer campaign cap, and expected net value must be positive.

The cap covers this campaign only; no annual cumulative limit is claimed without a cross-campaign spending ledger.
The morning product's 06:00-11:00 restriction is included in both Arabic and English reasons.
The source export cannot establish off-peak preference, incremental usage or actual Almadar subscriptions.
Each customer gets the best feasible candidate by assumed net value, with preference then offer ID as tie-breaks.
Greedy allocation ranks customers by that net value, then subscriber ID, skipping a best candidate that does not fit the remaining budget.
This is not a globally optimal knapsack solver and does not replace an unaffordable candidate with a smaller alternative.
Delivery costs round up to integer dirhams and the budget rounds down.

The comparison spends exactly the targeted spend in expectation, not merely the same maximum budget.
Untargeted allocation assigns the same inclusion probability to all feasible active, scored, non-holdout subscribers, including low-risk and nonpositive-value candidates.
Risk-only allocation orders the same pool by churn probability, with a fractional last inclusion probability when needed to match spend.
Both use the same per-customer candidates and retain relevance, eligibility, value-cap and cannibalisation constraints.
Fractional expected counts exist only in the report, never in the executable proposals.
The comparison measures the assumptions' consequences; a randomized campaign is still required to measure real effects.

A seeded SHA-256 lottery produces reproducible holdouts independent of row order or batch size.
The realized holdout is approximately 10%, not a forced exact row count.
The holdout is retained in the campaign snapshot and never receives an offer.

`churn decide` writes proposals and an empty release file in a new campaign directory.
The authoritative JSON stores inputs, policy, catalogue, decisions and a content fingerprint, plus review events.
CSV files are derived views and are never trusted as review inputs.
`churn approve` requires a named reviewer; it can approve or reject selected pending IDs or all pending proposals.
Only approved rows reach `released.csv`, which omits internal risk and monetary fields.
Each event records subscriber, reviewer, UTC time, decision, optional note and campaign fingerprint.
Duplicate reviews, unknown IDs and attempts to review no-offer or holdout rows fail without partial changes.
An exclusive local lock prevents concurrent review writes; JSON is replaced atomically before derived files are refreshed.
After an interruption, `--refresh` regenerates derived files without approving other pending rows.
The CLI does not revoke a released offer or send/provision one.
Checksums detect accidental changes; local files and reviewer names are not an authentication boundary, which remains T15 work.

This checkout has no real gated churn bundle, so the committed report is an explicit `--tiers-only` readiness run over all 30,000 unlabeled customers.
It records 27,582 active customers without risk, 2,418 already-silent customers, 2,965 holdout assignments, zero proposals and zero spend.
Those zero results support no campaign-effectiveness claim.
The positive-proposal and approval paths are verified with hand-made unit and integration inputs, including the existing synthetic test bundle.
No real customer campaign was approved or released during implementation.

## 21. A read-only integration service, with separate keys per consumer

Date: 2026-09-21.

Ali took T15 after T10 and T11, so the chatbot and the copilot have something to call.
The module already had two generated contracts and an approved-only release file; what it did not have was a way for another team's service to reach them over the network.
Decision 10 said an HTTP service would be built only when a teammate's service needed to call us, and the team platform (decision 17) is now that need.

FastAPI, uvicorn and httpx are added to the dependencies.
This is the first dependency added since the module was built, so it is recorded here rather than treated as routine.
FastAPI earns its place for one reason beyond routing: the response models generate the OpenAPI page at `/docs`, so the integration documentation is produced by the same code that answers the request and cannot drift from it.
That is the rule the input and output contracts already follow.
uvicorn runs the app for `churn serve`, and httpx is a test-only dependency that FastAPI's test client requires.
No container, no process manager, no database and no message queue were added; the service is one command that reads files.

The service has no write path at all.
Every route is a GET, a test asserts that the generated OpenAPI document contains no other method, and nothing can be created, changed or approved through it.
An offer appears only after a named reviewer approved it with `churn approve` (decision 14), and no language model sits anywhere in the path (decision 17).

The approved campaign is read from the authoritative `proposals.json` and filtered through `released_campaign`, not from the derived `released.csv`.
T11 made the JSON the authority so that editing a CSV could not approve an offer, and a service that served the CSV would have handed that authority straight back.
A campaign that fails validation serves no offers at all rather than falling back to the derived file.

Access control uses one key per consumer, sent in the `X-API-Key` header and compared in constant time.
Each key is accepted only on its own endpoints: the chatbot key opens `/catalogue` and `/subscribers/{id}/retention`, the copilot key opens `/portfolio/summary`, and either key on the other's endpoint is refused with 403.
A leaked chatbot key therefore cannot read the portfolio.
Both keys come from the environment, have no default and no development fallback, must be at least 24 characters and must differ from each other; the service refuses to start otherwise.
This closes the boundary that decision 20 left open, where local reviewer names were explicitly not an authentication boundary.
It is transport-level access control between two trusted internal services, not per-user authorization, and it assumes the service is not exposed to the public internet.

`/health` takes no key.
A liveness probe has no secret to offer, and the response holds only versions, counts and timestamps, never customer data.
It reports "ok" only when the bundle predicts its stored sample row and there is a portfolio to summarise, because a degraded service that reports "ok" leads the copilot to quote numbers from an export that is not there.
Loaded and usable are reported separately, following Ali's serving lesson that an artefact which deserialises is not an artefact that predicts.

The chatbot is never told a churn probability, a risk band or a value figure, and the response model forbids any field that is not declared.
It is also not told the reviewer's name: the chatbot speaks to the customer, and which employee approved a campaign is not the customer's business.
A rejected proposal, an unreviewed proposal, a subscriber with no proposal and a subscriber with no campaign all return the same 404 with the same message, so nobody can infer that an offer was considered and refused.

Identifiers are pseudonymous by contract, and an ID shaped like a Libyan mobile number is refused with 422 rather than looked up.
The pattern and a `pseudonymize` helper are ported from `Ali_Branch`'s `src/cvm/ingest/hashing.py` into `src/prepaid_churn/privacy.py` (port log step 9).
Ali's three corrections to the naive pattern are kept with their reasons, and a test hashes 500 identifiers to show that the service's own digests never trip the check.
The helper requires a salt of at least 16 characters, because an unsalted digest of a nine-digit number is reversed by hashing every number in the range.

`lyd_at_risk` is the 12-month value weighted by each customer's churn probability, so it is an expected loss under the T10 scenario assumptions rather than the value of everyone in a band.
Reporting the unweighted sum would inflate the copilot's headline by an order of magnitude, which is the mistake Ali's own cohort endpoint documented.
When an export carries no risk estimate the figure is null, never zero, and `risk_available` says so.
The success thresholds and test metrics travel with the summary from the bundle's release gate, so the copilot quotes the frozen T7 evaluation rather than anything recomputed at request time.

Every output is loaded once at startup and held in a frozen state.
An endpoint that opened a file per request would eventually read a campaign that `churn approve` was halfway through rewriting.
The cost is that a newly approved campaign is served only after a restart; `/health` reports the campaign fingerprint and load time so an operator can see exactly what is being served.

The service was run against this checkout on 2026-09-21.
It reports degraded with no bundle, serves all 57 catalogue packages, summarises the 30,000-row tiers-only export with `risk_available` false and every `lyd_at_risk` null, and returns zero approved offers, because no real campaign has been approved.

## 22. A demo app that reads the outputs and can approve them

Date: 2026-09-21.

Ali took T14 after T15, so the module has something a person can be shown rather than an OpenAPI page.
The app is four Streamlit screens in `app/`, over a new pure module `src/prepaid_churn/demo.py`, and it follows the same rule as the service: it reads what the pipeline wrote and recomputes nothing.
Loading goes through `service.load_state`, so the screens and the T15 endpoints answer from one state and cannot drift apart.
The one thing it may write is a review, and it writes it through `campaign.review_file` exactly as `churn approve` does, with the same lock, the same atomic replacement and the same named audit event (decision 14).

Streamlit is added to the dependencies.
Charts use Altair, which Streamlit already installs, so no separate plotting dependency was added.
`streamlit run` is a development server for a demo, not infrastructure: there is no container, no process manager and no database.

The budget is a preview, not a decision.
The ticket asks for a budget control, and the screen provides one by re-running T11's allocation over the campaign's own stored inputs, catalogue and policy with only the budget changed.
Nothing about that preview is written, and nothing in it can be approved.
Approval always acts on the campaign `churn decide` wrote, so a reviewer cannot approve a row a slider produced.
A different budget becomes real only by running `churn decide --budget` into a new directory.

Two environment variables, `PREPAID_CHURN_CAMPAIGN_DIR` and `PREPAID_CHURN_PORTFOLIO`, choose which campaign and which export the app shows.
Both genuinely vary: `churn decide --output-dir` writes every campaign to its own directory and `churn tiers --output` writes every export to its own file.
Without them the app could only ever show the first campaign ever made.

Reporting rules carried over from decision 21, because a screen misleads faster than an API:
- Expected churners is the sum of calibrated probabilities, not a count above a threshold, and it keeps a decimal while it is small, because 0.7 expected churners is not 1.
- Revenue at risk is the 12-month value weighted by each customer's own churn probability, never the value of everyone in a risky band.
- Every figure that needs a churn probability is blank, not zero, when no bundle scored the export, and a banner says so on each screen.
- Each screen names the outputs it is missing and the command that produces them.

The ticket's acceptance is that every screen is opened in a browser, including with a single customer, because two of `Ali_Branch`'s late bugs were only visible on screen.
That was done on 2026-09-21 against the real 30,000-row export, against a five-customer campaign and against a one-customer campaign.
It found five defects that the unit tests had not: an alphabetically sorted category axis that put the value tiers in a meaningless order, a typed ID that silently overrode the random-pick button, a fractional tick axis for whole customers, a plural that read "1 customers", and an unreviewed proposal reporting "reviewed by nan" because pandas had cast the absent reviewer to text.
All five are fixed and four of them now have tests.
The exercise is the reason the ticket required it.

The SMS preview reports parts, not characters alone, and that is the point of the screen.
A single Arabic character forces the whole message into UCS-2, where one part is 70 characters instead of 160.
The approved message on the checked campaign is 102 characters and therefore sends, and bills, as two parts, which is a real finding about T11's reason text rather than a display detail.

The customer message states the package and the reviewer's reason and nothing else.
It carries no churn probability, no risk band and no value figure, and the reviewer's name is not in it either: the chatbot and an SMS both reach the customer, and which employee approved a campaign is not the customer's business.
The subscriber screen refuses an ID shaped like a Libyan mobile number before looking anything up, because a Streamlit widget value reaches the session state and the server log first.
