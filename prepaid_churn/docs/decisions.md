# Decision log

Why the churn module looks the way it does.
Newest decisions go at the bottom.
Every entry says what was decided, why, and what it rules out.

## 1. We do not build on Ahmed's `customer_churn_prediction/` module

Date: 2026-09-13.
The reasoning below was reordered on 2026-09-25; the decision and every finding are unchanged.

Taha asked for an independent audit of the existing churn module before reusing it.

**The deciding reason is the data, not the code.**
The Maven and IBM Telco datasets describe a fictional company, which IBM states itself, and both are postpaid and a single snapshot in time.
This module serves prepaid subscribers of a Libyan operator, where there is no contract to cancel and churn is a monthly behaviour that has to be observed rather than an event that gets recorded.
No amount of repair turns invented postpaid contract records into prepaid behaviour, so a different foundation was needed whatever state the code had been in.

**The audit also found faults in the code.**
They are listed here because they are the mistakes this module was then built to avoid, not because they decided the outcome.
Every one of them could have been fixed; the dataset mismatch could not.

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

Each fault above has a matching rule in this module.
The leak became the no-leakage rule of T4 and T5, the in-sample headline became the single frozen test of T7, the uncalibrated probabilities became the mandatory calibration check of decision 13, and the tuned threshold became the rule that every choice is made on validation customers only.

Ahmed's folder stays untouched on this branch.
If `prepaid_churn/` works, the team deletes the old folder later.

This entry is not a judgement of Ahmed's work as a whole, and the audit was of the code in the repository rather than of the person who wrote it.

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
- It is **prepaid**, like the Libyan market (both Libyan mobile operators are prepaid), and churn means inactivity, not a cancelled contract.
- It is a **monthly panel** (months 6, 7, 8 plus a month 9 label), so features can come from months before the label month.
- It has real versions of the signals a Libyan operator would use: on-net and off-net minutes, incoming and outgoing calls, recharge count, amount and date, night packs, social-network packs, roaming, and age on network.

Rejected:
- IBM Telco and Maven: fictional, postpaid, one snapshot.
- Cell2Cell and the 100k Teradata data: real but US postpaid from around 2000, with churn deliberately enriched to about 29% and 50%.
- Iranian UCI churn: only 3,150 rows and a mix of pay-as-you-go and contract customers.
- KKBox: real and time-stamped but music streaming, not telecom.

The trade-off we accepted, stated plainly because it is the largest limitation in the project:
- **Four months is short, and we chose it anyway.**
  Two months feed the features, one carries the label, and one is spare.
  That leaves one month-to-month change per customer and no seasonality, no trend and no long history.
  Cell2Cell has longer histories, so this was a real choice rather than the only option.
  We took prepaid behaviour over history length, because a model of postpaid contract customers cannot be repointed at a prepaid market (decision 1), while a short history still supports the question we actually ask.
  Almost every later limitation traces back to this line.

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

Chapters 7 and 10 (NLP and LLMs) belong to the chatbot module.
Chapters 8 and 9 (deep learning, RNN and GAN) are covered by the teammates' parts of the project; this module's experiments for them were removed on 2026-09-26 (decision 44).

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
- Nothing in the repo contains real Libyan operator packages or prices; only tower locations and operator codes (in the antenna module).
- One Libyan operator publishes its data packages on its website; the other's site blocks automated requests but works in a normal browser.
  T16 builds a real package catalogue from these official sources, with a collection date on every row.
- The Orange Belgium Churn-Uplift dataset in the action plan is real: 11,896 customers of a real phone retention campaign with a random control group.
  It is postpaid, its features are anonymized, and its license is non-commercial (CC BY-NC-ND 4.0), so this module does not use it.

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
- It also holds real, valuable work: the operator's published packages, prices, recharge cards and emergency credit rules, a careful offer engine design, an HTTP contract for the chatbot and copilot with grounding rules for LLMs, and a list of serving bugs found the hard way.

Decided:
- This module stays the base: real data, `uv`, and the frozen T7 champion.
- `Ali_Branch` is **not** merged with git.
  Its history is unrelated and its root-level files would collide with the team repo.
  Pieces are ported by hand, each one logged in `docs/ali_branch_merge.md` with its source path, and the commits credit Ali as co-author.
- `Ali_Branch` stays on GitHub untouched, as the record of his work.

Taken (the ticket that uses each piece is in brackets):
- Operator catalogue, tariffs, recharge cards and emergency credit rules (T16).
- Mapping money onto the operator's scale (T18).
- Offer engine design: the real catalogue as the action space, "no offer" as a real option, the guardrails including the cannibalisation guard keyed on the bundle a customer holds, the equal-spend comparison, the holdout and the decision log (T11).
- Serving lessons: everything a scoring run needs travels inside the bundle, pinned library versions, a smoke prediction at load time, and one-row batches as a test case (T8).
- The API and screen designs, and the grounding rules for LLM consumers (T14, T15, T20).
- Prepaid value segmentation (T10), the emergency credit rules (T19) and the model card template (T9).

Not taken, and why:
- The generated population and its formula labels, and every result measured on them: decision 7, the metrics would measure the formula.
- The repayment model for emergency credit: no real repayment data exists.
- Cox and random survival forests: our data is monthly, so there is no time-to-event to model.
- DuckDB feature store, MLflow, Docker, conda and the eight-model benchmark: decision 7, not needed at this size.
- Cell2Cell, IBM Telco, UCI Iranian, Hillstrom and Online Retail as data sources: decisions 5 and 7.

Conflicts between the two efforts, and how they are settled:
- Syllabus coverage: `Ali_Branch` removed chapter tracking; it stayed here, because SIC grades it (decision 8), until the teammates' parts took chapters 8 and 9 (decision 44).
- Data in git: `Ali_Branch` never commits data; the raw Kaggle files stay committed here (decision 9).
- Churn definition: `Ali_Branch` uses "30 days without a top-up"; we keep the usage-based rule, because the only real label (Kaggle's month 9) uses it.

## 16. A real Libyan operator's catalogue, and real customers shown in its terms

Date: 2026-09-19.

A real Libyan mobile operator, not named in this project (decision 45), is the only one with real, confirmed data here: its published packages, prices, recharge cards and emergency credit rules, collected by Ali on 2026-09-18.
The other Libyan operator has none yet, so this updates decision 11: the module targets the first, and the other can be added later as more rows in the same catalogue.

How the two datasets meet:
- The churn model keeps training on the real upGrad customers in their original units.
  The T7 champion stays frozen.
- The business layer (value, offers, emergency credit, app) shows each real customer in the operator's terms (T18): money in LYD, the operator's bundle they would hold, and their usual recharge card.
- The conversion is one documented scale anchored on stated assumptions, kept in one file with a status per value (confirmed, assumption or estimate).

What the report must say: the behaviour comes from a real prepaid operator in another market; the prices, packages and money are the operator's; real use needs retraining on the operator's own export (decision 11).

## 17. The customer MVP comes first, built to plug into the team platform

Date: 2026-09-19.

The instructor's review of the action plan asked to:
- narrow the MVP to one measurable customer use case, so the three weeks allow credible integration and testing;
- protect customer data through de-identification, access control and a human approval step for retention actions;
- use the employee copilot only as retrieval-grounded Q&A over approved model outputs and documentation, with citations and refusal when evidence is missing, never making network or customer decisions.

The team's final goal is one platform: GIS planning, network ML, this customer module, a customer chatbot and an employee copilot.
In the action plan, Taha owns the chatbot, the copilot and the integration, and Ali owns customer intelligence and the chatbot.

Our MVP use case: "Which active prepaid customers are likely to stop using their line next month, and which approved operator offer should each one get?"
The MVP path is T16, T8, T18, T10, T11, T15, T20, T14 and T9.
T19 comes after the MVP works end to end.

How the module links to each part of the platform (extends decision 10):
- **Customer chatbot:** reads the operator's catalogue (T16) and, for the one subscriber it is talking to, the approved offer and its reason (T15).
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

All T11 policy and delivery-cost assumptions are in `data/operator/retention.toml`.
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
The source export cannot establish off-peak preference, incremental usage or actual operator subscriptions.
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

## 23. Emergency credit advice from recharge behaviour, with no repayment model

Date: 2026-09-21.

Ali took T19 as the first experiment after the MVP.
The operator sells two emergency credit products, both confirmed from its own documents and recorded by T16.
The airtime advance is 1, 3 or 5 LYD, offered when the balance is at or below 0.5 LYD.
The data advance is a flat 5 LYD for 2 GB over 72 hours, offered when the balance is at or below 1 LYD.

`src/prepaid_churn/advance.py` advises a limit and grants nothing.
A limit reaches a customer only if a person approves it, exactly as a retention offer does (decision 14).
No new dependency was added.

There is no repayment model and there will not be one until an operator supplies repayment history (decision 15).
Nothing in the module estimates a probability of repayment, so no figure in the report is a default rate.
`Ali_Branch` also caps by loyalty tier, by a share of customer value, by monthly cumulative exposure and by a chronic-distress screen.
None of those were ported: they need a repayment model, an advance history, a tenure tier or balance-level fields that this data does not contain.
The other Libyan operator's credit loan, with its tenure gate, grace period and line reset, is a different product and is not quoted here.

One rule is applied: never advise a debt larger than 0.6 of the customer's typical top-up.
The fraction is ported from `Ali_Branch` with his reason intact, and the code refuses any fraction at or above 1.
At 1 a debt exactly equal to the typical top-up would be allowed, which is precisely the customer the rule exists to protect.

The zero-residual finding is computed rather than asserted.
The smallest recharge card is 5 LYD, and so are both the data advance and the top airtime rung, so clearing either leaves 0 LYD.
A test pins this, and a second test shows the finding would retire itself if the operator ever sold a larger smallest card.
The claim it supports is a disincentive to recharge, not a locked door: an exact equality is weaker evidence than an impossibility would be, and nothing here measures how often the disincentive bites.

The basis for "typical top-up" is an adaptation, not a port.
`Ali_Branch` asks for the modal top-up, because a mean is dragged up by one salary-week recharge that will not repeat.
This dataset holds monthly totals and counts and never individual transactions, so no mode can be computed at all.
The average top-up in the quieter of the two window months is used instead: closer to the habitual amount than an average across both, and never larger, so it cannot widen the advice.
That choice moves the result by more than twenty points, so the report carries a sensitivity table across the quieter month, the mean and the busier month rather than burying the assumption.
Both months travel in the output beside the verdict, so a reviewer sees the behaviour the advice was read from.

The result on the 30,000 unlabeled customers is a finding about the product rather than about the rule.
This base tops up often and in very small amounts: the median typical top-up is 1.89 LYD, against a median of five to six recharges a month.
The smallest advance needs a top-up of at least 1.67 LYD to clear while leaving balance, so 46.1% of customers are advised nothing at all.
The flat 5 LYD data advance needs 8.33 LYD and is advised for 4.65%, although the operator offers it to anyone whose balance is low enough.
Those shares are computed on real upGrad behaviour from another market and are not a claim about Libyan customers.

## 24. One branch again: `tahaDev` carries both efforts

Date: 2026-09-21.

Decision 15 said Ali's work would be ported by hand and never merged with git.
The reason was that `Ali_Branch` was an orphan: no commit in common with this branch, a different project in its tree, and root-level files that a merge would have dropped into this repository.
That reason ended on 2026-09-20, when Ali adopted `tahaDev` `bfb28ab` as his tree (decision 18) and built his review, T10, T11, T15, T14, T9 and T19 on top of it.
`Ali_Branch` is now thirteen commits ahead of `tahaDev` and shares its whole history, so the two branches can be joined by a fast-forward, with no merge commit and no conflict to resolve.

Checked before taking it, on Taha's machine:

- The tree of Ali's baseline commit `22aefc8` is identical to `bfb28ab`, byte for byte (`git diff` is empty, same tree hash `a428bfe3`), so nothing of ours was silently replaced.
- 379 tests, `ruff check` and `ruff format --check` pass.
- The full pipeline rebuilds from the committed data in about a minute and reproduces the frozen champion: bundle `lightgbm-2026-09-19-ef9430fb`, tiers `tiers-v1-cd15525cb3ef`, and `git status` clean afterwards, so no committed report moved.

So `tahaDev` was fast-forwarded to `Ali_Branch` instead of re-typing 9,000 verified lines by hand.
Hand-porting still governs anything from Ali's original CVM tree at `06890f6` and earlier, which remains unrelated history; the port table in [ali_branch_merge.md](ali_branch_merge.md) is still the record for that.

From here there is one branch.
Both of us work on `tahaDev`, claim a ticket by writing a name in its Owner field, and pull before starting.
`Ali_Branch` stays where it is as the record of how the two efforts met; it is not deleted and not worked on.
Decision 18's instruction to deliver on `Ali_Branch` ended with that delivery.

One consequence Taha has to know about: Ali's review also fixed Ahmed's `antenna_cell_placement/` module and added `CODE_REVIEW.md` at the repository root, so those changes are now on `tahaDev` too.
They are Ali's work, reviewed by nobody in this module, and they belong to Ahmed's module.
Nothing goes to `main` without the team agreeing, and those files are the first thing to raise when it does.

## 25. The example client is copied, not imported, and needs nothing installed

Date: 2026-09-21.

T20 asks for an example client, and the obvious thing would be a small package the chatbot and the copilot import.
That would rebuild the coupling the service exists to prevent (decision 21): a consumer that imports our code is pinned to our Python version, our dependencies and our release day, and can reach past the endpoints into the functions behind them.

`src/prepaid_churn/client.py` is therefore written to be copied into the consumer's own repository.
It uses only the standard library, so it adds no dependency here and none there, and it takes the base URL and the keys as arguments rather than reading our configuration.
`httpx` stays a test-only dependency.

It duplicates exactly one thing from the service, the `X-API-Key` header name, because a copy living in another repository has nothing to import.
`tests/test_client.py` compares the two constants, so the duplication cannot drift silently.

`churn check-integration` runs that client against a running service and prints what every consumer sees, including the four refusals: the wrong key on each side, no key at all, and an ID shaped like a Libyan phone number.
It exits 1 when a refusal did not happen, so the seam is checked by a command rather than by reading a document and trusting it.
The contract test starts the real app on a real port and runs the same client against it, rather than calling the app in process as `test_api.py` does, because the thing T20 is meant to prove is the seam and not the app.

What the example deliberately does not do: no retry, no backoff, no connection pooling, no caching and no authentication flow.
Each consumer's own framework has those, and an offer must not be cached anyway (decision 14 and the grounding rules in [integration.md](integration.md)).

## 26. The copilot can look up one subscriber

Date: 2026-09-21.

T20's acceptance is that the consumers get what they need, so the walkthrough asked the questions each consumer really gets rather than only checking that the documented calls answer.
The chatbot came through it: a customer asks what is available and whether anything is waiting for them, and `/catalogue` and `/subscribers/{id}/retention` answer both.
The copilot did not.
An employee with a customer on the phone asks "what do we know about this one", and the service could answer only with portfolio totals.
A copilot that cannot answer the question it was opened for is not integrated, whatever the endpoint list says.

`GET /subscribers/{id}/risk` serves one row of the same export the summary already aggregates: the calibrated probability, the risk band, the model's own plain-language reasons in its own order, the value tier, the three 12-month scenarios, the assumed monthly spend, and the versions and timestamp behind all of it.
Nothing is computed on the request, so it cannot disagree with the summary.

The fields this endpoint returns are exactly the ones the chatbot may never see (decision 21).
That is the point of two keys: the employee deciding what to do for a customer needs the risk, and the customer does not need to be told how likely the operator thinks they are to leave.
Both lookups sit under `/subscribers/{id}`, so each key is refused on the other's path and a test proves it on a real socket.

Its 404 means something different from the offer lookup's, and the guide says so.
There, 404 hides whether an offer was considered and refused.
Here it only means the subscriber is not in the scored export, because nothing about a subscriber is withheld from the copilot once they are in it.

What was not added, although the walkthrough asked for it:

- A list or search endpoint ("the 200 riskiest customers").
  Serving customer-level rows in bulk over HTTP is what decision 17's de-identification rule exists to prevent, and the analyst case is already covered by the committed exports and the demo app.
- The package a customer holds and their spend, for the chatbot.
  The operator view is this module's assumption (decision 16), not an operator fact, and the operator's own systems answer it correctly and in real time.
- The emergency credit advice (T19).
  It is a proposal for a person, and no review step exists for it yet; a credit limit needs an approval as much as an offer does (decision 14).
- The review queue.
  A read-only service should not become the place where campaigns are watched; `churn approve` and the demo app own that.

Each one is written in [integration.md](integration.md) with its reason, so a consumer asks instead of building a workaround.

## 27. Removed

Removed on 2026-09-26 with the experiments it belonged to (decision 44).

## 28. Removed

Removed on 2026-09-26 with the experiments it belonged to (decision 44).

## 29. Removed

Removed on 2026-09-26 with the experiments it belonged to (decision 44).

## 30. Removed

Removed on 2026-09-26 with the experiments it belonged to (decision 44).

## 31. The Mix families leave the catalogue, and a removal is recorded rather than silent

Date: 2026-09-22.

Ali confirmed that the operator no longer sells the five Mix families, answering the question T16 left open on 2026-09-19.
He had removed the same 20 packages from his own catalogue on 2026-09-18 in commit `62040af`, which showed the removal was deliberate but never recorded a reason.
The catalogue now holds 37 packages in 12 families, which is exactly what `Ali_Branch` held, so the difference T16 pinned with a test is closed.

Deleting the rows alone was not acceptable.
The files in `data/operator/source/` are byte-for-byte copies of the operator's own export (port step 1), and `check_against_source` required every row in them to appear in the catalogue exactly once.
Editing the source file to match would have destroyed the evidence, and relaxing the check would have allowed any package to disappear unnoticed, which is precisely how the Mix question arose.

So a removal is now recorded.
`data/operator/excluded.csv` holds one row per package that the operator file lists but the operator no longer sells, each with its source row, a reason, the person who decided and the date.
`check_against_source` requires every source row to be either in the catalogue exactly once or recorded there, so the integrity guarantee is unchanged while the catalogue is free to shrink.
"Unknown" in that check now means a row that is not in the operator file at all, which an excluded row still is.

Removing Mix narrows the action space, and that is a real consequence rather than a detail.
They were the only metered packages carrying both data and voice.
What is left with voice is the Family share tier, which the membership guard already excludes because we cannot establish eligibility, and the 1 LYD morning pass, which the cannibalisation guard blocks above the base monthly rung.
A voice-only customer above that rung therefore has no eligible offer at all.
`tests/test_retention.py` now pins that as the expected answer, with the reasoning written beside it, instead of asserting that a Mix package is chosen.

The committed `reports/decisions.md` was regenerated, and only the 20 Mix rows left its per-offer table.
Every headline number is unchanged, because the readiness run proposes no offers at all.

## 32. The decision report is written beside its campaign

Date: 2026-09-22.

Taha found that `churn decide` rewrote the committed `reports/decisions.md`, so running the documented command left a tracked file dirty and could replace the recorded readiness run with another run's numbers.
Every campaign needs its own output directory, and a run may use a different budget, so the report is campaign-specific and does not belong at a fixed path in the repository.

`--report` now defaults to `decisions.md` inside `--output-dir`.
Passing `--report` explicitly still writes wherever it is told, which is how the committed readiness report is refreshed on purpose.
A test runs the documented command and asserts that the committed report is untouched.

The other report-writing commands keep their fixed defaults, because each one regenerates the same committed file from the same committed input; the fresh-clone check of T9 depends on exactly that.

## 33. Readiness must cover the served answers and the real review screens

Date: 2026-09-22.

Ali asked whether every ticket was finished and requested an end-to-end run with the available data.
All tickets are Done, but the initial checkout had no local churn bundle, and a passing unit suite alone could not show what an evaluator or consumer would receive.
The frozen README rebuild reproduced the expected artifacts without changing existing reports, and the live run is recorded in [reports/end_to_end.md](../reports/end_to_end.md).
No model choice was changed because of this check.

The serving boundary must preserve a literal `NA` subscriber ID just as the input and campaign boundaries do.
Pandas' string dtype still recognises missing-value tokens, so the service portfolio and demo view use an ID converter while numeric columns keep their missing-value behavior.
Empty or duplicate portfolio IDs are rejected at startup rather than letting a lookup return an arbitrary row.

An approved offer can disappear from the current catalogue after the immutable campaign was reviewed, as the Mix removal made concrete.
The service withholds such rows and reports degraded health; it does not invalidate or rewrite the campaign's audit history.
A new campaign and review are needed to propose a current package.
The dashboard's approved-message selector reads this same filtered service state.

The API requires printable ASCII credentials without spaces and rejects non-ASCII presented credentials with 401.
This prevents a malformed header from reaching `compare_digest`, whose string comparison raises on non-ASCII input.
There is no change to the two-role access model.

The integration checker previously counted only refusal failures, so degraded health or unavailable risk could still end with "Every check passed."
Health, available portfolio risk and the model release gate are now readiness requirements too, and a failure returns exit code 1.
Unavailable LYD at risk is not printed as zero.
Its Arabic output is UTF-8 even when redirected on Windows, where the default code page caused the actual CLI acceptance run to crash.

The dashboard's actual scripts are now exercised on the shared hand-made fixtures with Streamlit `AppTest`.
The review-to-message test covers empty-selection refusal, individual approval, cache refresh and both message languages.
Live acceptance reviews used a separate QA copy; the original 2,911-proposal campaign received no approvals.

Delivery remains on `Ali_Branch` because Ali explicitly forbade commits or pushes to `tahaDev` in this task.
That current instruction takes precedence over the earlier shared-branch convention in decision 24.

## 34. The app may propose a campaign, and every campaign keeps its own directory

Date: 2026-09-22.

Taha used the demo app and found three things wrong with it, all of them fair.
It was slow at everything, there was no way to create an offer without going back to the command line, and after approving fifteen offers there was nowhere to see what he had approved.

**Slow.** A campaign over the whole base is a snapshot of 30,000 customers, which is an 80 MB JSON file, and the app was reading it twice on every cold load and once more after every review.
Two fixes: the snapshot is now parsed once and handed to the service loader (`load_state(paths, campaign)`), and the app can propose a campaign over as few customers as it likes, which is what makes the file small.
A 500-customer campaign is 1.7 MB and loads instantly; the 30,000-customer one still exists and is still selectable, so nothing was taken away.

**No way to create an offer.** The app now runs the same decision path as `churn decide`: the frozen tiers, the gated bundle, the catalogue, the policy, the same guardrails and the same holdout.
The screen chooses two things only, who is considered and what may be spent.
It never picks a package, because the whole point of T11 is that a policy picks it against stated value assumptions, and it never approves what it proposed, because a named person has to (decision 14).
The Subscriber screen proposes for one customer the same way, which is how a real operator meets this: an employee has someone on the phone and asks what can be done for them.
Proposing for a customer the model scores at low risk correctly produces "no offer", and the screen says so rather than inventing something to give away.

Every proposal writes its own campaign directory and never appends to an existing one.
That is Ali's design in T11 and it stays: a campaign is an immutable snapshot of what was decided, with its own fingerprint and its own review log, and appending to it would make the fingerprint a lie.
The cost is a directory per proposal, which is why the sidebar now has a picker that lists them.

**Nowhere to see what was approved.** There is a Released screen now: the approved rows, the package beside each one, who approved it and when, the three files that hold it, and the one endpoint the chatbot reads it from.
It also says the service loads the campaign at startup, so a new release is served after a restart, which was true before and written nowhere a reviewer would look.

One more thing was wrong and is fixed: an empty selection in the approval box meant "approve everything", so a reviewer who clicked Approve with nothing selected approved every pending proposal in the campaign.
Reviewing everything is now a separate checkbox that says how many rows it covers, and an empty selection is an error rather than a mass approval.

## 35. Error bars on the frozen test numbers, and they change nothing

Date: 2026-09-25.

While recapping T4, Ali asked how sure we are of the published test numbers.
Every figure in `reports/evaluation_all.md` comes from one draw of 9,677 test customers, 421 of whom churned, and none of them had an interval.
"0.348 beats 0.277" was stated as a fact without saying how much of it could be the luck of which customers landed in the test group.

`churn uncertainty` answers that with a bootstrap.
It resamples the frozen test predictions 2,000 times, 9,677 customers drawn with replacement each time, seed 42, and reports the 2.5th and 97.5th percentiles of each measure.
Both models are scored on the same resampled customers every time, so the difference between them is paired.

It is built so that it cannot change anything.
It trains, calibrates and chooses nothing.
Only the champion's calibrator is saved, so the baseline's is re-derived by repeating the validation-only freeze with the recorded date, and the command refuses to continue unless that repeat reproduces the saved champion's test predictions exactly.
Its estimates match `reports/evaluation_all.md` to the last digit, and that report was not regenerated.
Reading the frozen predictions again is not a second evaluation: the models, the calibrators and every choice are the ones scored once on 2026-09-19.
No result of it may be used to justify a change to a model, feature or threshold.

What it found, from [reports/uncertainty.md](../reports/uncertainty.md):

- LightGBM PR-AUC 0.348, 95% interval 0.301 to 0.400; logistic regression 0.277, 0.238 to 0.324.
- The difference is 0.071, interval 0.040 to 0.102, and LightGBM scored higher in all 2,000 resamples, so the champion's lead is not luck of the draw.
- All four checks of decision 13 still pass at the unfavourable end of their intervals: capture at least 57.3%, PR-AUC at least 7.1 times the churn rate, a calibration gap of at most 0.5 points, and a lead over the baseline of at least 0.040.
- The baseline's own capture interval reaches down to 48.7%, below the 50% bar, so the baseline alone would not have been a safe release.
- The drop from validation to test, 0.458 to 0.348, is more than twice the half-width of the test interval, so the later month, Kaggle's label and the optimism of having chosen on validation move the numbers more than sampling luck does.

What it does not cover: training randomness, which would need models retrained on other splits and each scored on the spent test window, and a different month or operator, which only new data can measure.

## 36. The high-value flag stays, as a comparison tool only

Date: 2026-09-25.

The T4 recap found that `churn build-dataset --high-value` builds a dataset that no later command reads.
The product path (`bundle`, `score`, `tiers`, `decide`, the service and the app) always uses `data/processed/all/`.
The high-value slice in `reports/evaluation_all.md` does not come from the flag either: `churn evaluate` applies the same rule to the main test set, with its own 70th-percentile cutoff (`HIGH_VALUE_QUANTILE`).

It stays, for two reasons.
The upGrad case study this data comes from predicts churn only for high-value customers, the top 30% by average recharge over the first two months, and the flag is how our numbers can be set beside work that follows the case study.
Ours is computed among active customers only (decision 12), so the population is close to the case study's, not identical.
It is also small, tested and off by default, and removing it would reopen a settled choice for no gain to the product.

What changed is only the text, so nobody reads more into the flag than it does.
T4, the settled choices in TICKETS.md, the README and the model card now say that it exists for comparison and that the product never uses it.
It must not be carried through `churn evaluate` on this data: the test customers were scored once on 2026-09-19, so a model trained on the high-value dataset could only be tested by scoring them a second time.
The T7 slice, PR-AUC 0.383 at 2.9% churn, is the answer to how the model does on these customers.
`reports/dataset_high_value.md` stays as the record of the population's size: 13,708, 3,024 and 2,942 rows, with 4.2%, 4.4% and 3.0% churn.

## 37. Early stopping uses the train customers, not validation

Date: 2026-09-25.

The settled plan in TICKETS.md gave the validation customers three jobs: early stopping, calibration and threshold choice.
T6 moved the first job to a slice of the train customers and said so in its ticket, but no decision entry recorded the change, and the settled list kept the old wording until Ali's recap found it.
This entry records what was built; it changes no model.

What T6 does: LightGBM is fitted on 90% of the train customers while the other 10%, stratified by label with seed 42, decide when to stop (100 rounds without a better log loss).
The model is then refitted on all train customers with that tree count, 288 trees.

Why: the validation customers are then used only for the T7 choices (calibration, the champion and the risk bands), and T6's validation numbers come from customers its stopping rule never saw.
Stopping on validation and then calibrating and choosing on the same customers would have used them twice.
The cost is small: the tree count is chosen with 90% of the train customers instead of all of them.

The other LightGBM settings were set by hand and never searched: a learning rate of 0.03, 31 leaves, at least 50 customers per leaf, 80% row and column sampling and an L2 penalty of 1.0.
They are more cautious than LightGBM's defaults, and only the tree count is fitted.


## 38. A fifth release check for the next model: calibration where offers are made

Date: 2026-09-26.

Decision 13's calibration check compares the mean prediction with the observed churn rate, and the current champion passes it easily (0.13 points).
Its probabilities are still off inside the range.
On test, tenths 7 to 9 by predicted risk (1.1% to 10.9%) were expected to hold 98 leavers and held 134, about 3.7 standard deviations beyond chance, while the riskiest tenth was expected to hold 283 and held 259.
The two errors cancel in the mean, so the check could not see them.
A smaller version already shows on the validation customers the calibrator was fitted on (121 leavers against 100 predicted in those tenths), so part of it is the fixed shape of a sigmoid and part is the later month.

T11 multiplies each probability by money and proposes offers only in the high and medium bands, so calibration matters most inside those bands.
Counted by band from the frozen test predictions, read only as in decision 35:

| Band | Customers | Predicted leavers | Actual leavers | Actual against predicted |
|---|---|---|---|---|
| high | 450 | 199 | 173 | -13% |
| medium | 1,238 | 135 | 148 | +10% |
| low | 7,989 | 75 | 100 | +34% |

The largest miss is in the low band, where no offer is made.

The next model must also pass a fifth check, written down now, before that model exists:

5. **Calibration where offers are made:** in the high band and in the medium band separately, the number of customers who actually left must be within 20% of the number the model predicted (the sum of its probabilities), or within two standard deviations of chance if that is wider.
   The standard deviation of chance is the square root of the sum of p × (1 - p) over the band's customers: the spread the count would show if every probability were exactly right.

Why these levels:

- A 20% error in a band's predicted leavers is a 20% error in the money T11 expects from that band, and we take that as the most a retention team could accept when splitting a budget between bands.
  Like decision 13's levels, it is a minimum, not a number fitted to a result.
- The allowance of two standard deviations keeps a small band from failing by chance alone: a model whose probabilities are exactly right passes each band at least 95% of the time.
- The low band is left out because no money is spent there; its miss is reported in the model card instead.

Scope:

- It applies to every model evaluated after this date, starting with the retrain on an operator's own data (decisions 11 and 16).
- It does not apply to the current champion, whose gate was recorded on 2026-09-19 with decision 13's four checks.
  Measured the same way, the current champion would pass it (-13% and +10%).
- When the check is coded, the recorded gate must stay as it is, so the rebuild with `--chosen-at 2026-09-19` still reproduces bundle `lightgbm-2026-09-19-ef9430fb` byte for byte.
- Unlike decision 13's four checks, which were written after the test they were checked against, this one is written before the model it will judge is tested.

## 39. Ali works on Ali_Branch, and Taha's work arrives by merge

Date: 2026-09-26.

Decision 24 made `tahaDev` the one shared branch, and CLAUDE.md still told every session to work there.
Since 2026-09-22 Ali has worked on `Ali_Branch` only and forbidden commits or pushes to `tahaDev`.
Decision 33 recorded that for one task and the handoff called the older directions historical, but a new session reads CLAUDE.md first and would have pushed to `tahaDev`.
On 2026-09-26 `Ali_Branch` was 12 commits ahead of `tahaDev`, and `tahaDev` held one commit of Taha's (`f2cc724`, a session log and presentation material) that `Ali_Branch` did not.

So, until Ali and Taha agree on one branch:

- Ali's sessions work and push on `Ali_Branch` only, and never commit or push to `tahaDev`.
- Taha's work reaches `Ali_Branch` by merging `origin/tahaDev` into it, keeping Taha's history as the merge of 2026-09-22 did, and only when Ali asks for it.
- Taha keeps working on `tahaDev`; this entry does not decide which branch becomes the final one.

CLAUDE.md and the handoff now say this.

## 40. Reasons only for customers whose risk is above average

Date: 2026-09-26.

Every active subscriber used to get three reasons, including the 22,779 of the unlabelled base in the `low` band.
SHAP measures each factor's push away from the average customer, so even a very safe customer has a few small upward pushes.
A customer at 0.7% risk was given "Amount recharged on the last recharge day this month: 0", "Local incoming minutes this month: 31.5" and "Days since the last recharge, at the end of this month: 7", and the integration guide tells the copilot to quote reasons as they are.
An employee would read them as warning signs about a customer who is very unlikely to go silent.

So only `high` and `medium` subscribers, whose risk is above the validation churn rate, get the model's reasons.
A `low` subscriber gets one line, "Low risk: nothing stands out", the same way an already silent one gets "No calls and no mobile data this month".
The model, the probability and the band are unchanged; only the text beside them changed.
The reasons of the other bands are computed exactly as before, and a subscriber scored alone still gets the same row as inside a batch.

The model card and the integration guide also said the reasons are "written as sentences".
They are short labels with the customer's value, and both documents now say so.

## 41. The value scenario's assumptions do not hold, and T23 will replace it

Date: 2026-09-26.

T10's 12-month value assumes a customer keeps this month's churn risk for twelve months and never comes back after going silent (decision 19).
Decision 19 noted that the one-month probability had not been validated as a 12-month hazard.
Ali's recap checked both assumptions on the validation customers, whose month-9 outcome no decision had used, and left the test customers untouched.

Validation customers still active in month 8, by the band their months 6 and 7 gave them:

| Band | Customers | Risk predicted for month 8 | Churn in month 9 |
|---|---|---|---|
| high | 282 | 43.2% | 11.0% |
| medium | 1,034 | 10.6% | 8.1% |
| low | 8,044 | 0.9% | 3.6% |

- Risk does not stay constant: after a month it moves most of the way back toward the average, down for the high band and up for the low band.
- Silence is not always final: 28.1% of the 452 validation customers silent in month 8 were active again in month 9, close to the 26.3% of train customers found in T6.

What that does:

- Under constant risk, a customer's expected loss, risk times 12-month value, peaks near 20% risk and falls after it.
  At 40 LYD a month it is 17 LYD at 5% risk, 30 LYD at 20%, 23 LYD at 43% and 4 LYD at 90%.
- A 43%-risk customer is expected to stay 1.3 months; if those who stay kept the 11% measured in month 9, it would be 3.9 months.
- So the value of high-risk customers is understated and that of low-risk customers overstated, while counting no comebacks overstates every loss.
- T11 ranks candidates by risk × share saved × value - cost, so its order between medium- and high-risk customers, the "LYD at risk" figures and the campaign's equal-spend comparison all inherit these assumptions.

Nothing changes before the presentation.
The tiers report, the model card and T10 now say that the assumptions fail, and ticket T23 replaces the scenario with one built on measured risk after the first month and on comebacks.
The rates T23 needs come from validation customers only; the churn model, its thresholds and the spent test window stay as they are.

## 42. The ARPU anchor moves from 40 to 70 LYD

Date: 2026-09-26.

Every LYD amount in the module is a source-currency amount times one rate: the ARPU anchor divided by the mean monthly recharge of the customers active in month 8 of `train.csv`, 537.17 (T18, decision 16).
The anchor was 40 LYD, a team estimate set just above the Net 20 bundle price of 35 LYD and chosen by Taha on 2026-09-19.
Ali replaced it with 70 LYD on 2026-09-26, from a market report.

Source: Mordor Intelligence, Libya Telecom MNO Market, public summary read on 2026-09-26.

- Data and internet services were 44.9% of Libyan mobile operator revenue in 2025.
- Data use is projected to pass 12 GB per subscriber a month by 2030.

Derivation, with the operator's own monthly bundle prices from `offers.csv` (Net 10 at 30 LYD, Net 20 at 35 LYD):

- 12 GB a month costs about 31 LYD by linear interpolation between those two bundles, or 35 LYD when the 20 GB bundle is bought.
- Divided by the 44.9% data share, that is 69 to 78 LYD a month in total; 70 LYD is taken, near the low end.

What the estimate is not, as the review in this session pointed out:

- The 12 GB is a projection for 2030 and the 44.9% is for 2025, not measurements of today's average subscriber.
- Dividing one customer's data spend by a market-wide revenue share assumes every customer spends like the whole market, and most prepaid SIMs do not buy a 10 to 20 GB bundle every month.
- So 70 LYD may be high for the average prepaid SIM; 40 LYD was no better founded, because it was also a bundle price rather than an average.

It stays an `assumption` in `data/operator/market.toml` until an operator or regulator figure replaces it: mobile service revenue divided by mobile subscriptions, from one source and one year.

What changed, all from that one number:

- The rate moves from 0.074464 to 0.130313 LYD per source unit, so every LYD amount is 1.75 times larger.
  The viewed base now spends 68.94 LYD a month on average instead of 39.39, and 66.8% of active customers are nearest the 5 LYD card instead of 88.9%.
- The tier cutoffs in LYD scale with it but every customer keeps the same tier, because the tiers rank customers; the artifact version moves from `tiers-v1-cd15525cb3ef` to `tiers-v1-efc9739afad4`.
- T19 advises more: the median typical top-up is 3.30 LYD instead of 1.89, 30.6% are declined instead of 46.1%, and the data advance suits 18.3% instead of 4.65%.
- A 1,000 LYD campaign over the 30,000 unlabelled customers proposes 2,954 offers instead of 2,911, with 11,733 LYD of assumed net value instead of 6,387, because values grow while the operator's catalogue prices do not.
  At the same spend, targeting by risk alone is valued at 9,074 LYD and random at 2,298; 2,803 of the offers are still the morning pass.
- The churn model, its thresholds, its reports and the spent test window are untouched, because the model never sees LYD.

## 43. The holdout is a permanent control group

Date: 2026-09-26.

T11 holds out about 10% of customers from every campaign with a SHA-256 lottery over the subscriber ID and the policy seed, 42 in `retention.toml`.
The seed never changes, so every campaign holds out the same customers: 2,965 of the 30,000 in the unlabelled base, who never get a retention offer.
Nothing said whether that was intended; Ali's recap of T11 made it a choice.

From now on it is deliberate:

- The same customers stay out of every campaign as a permanent control group, a common design in customer marketing, sometimes called a universal control group.
- It gives the cleanest long-run measure: after several campaigns, churn among customers who were offered bonuses can be compared with churn among customers who never were, and the model chose neither group.
- The cost is that about 10% of customers never get a retention bonus; they keep everything else the operator sells.
- Changing the seed would reshuffle the group and end that comparison, so the seed changes only with a new decision entry.

Review it after the first measured campaign: the fraction can shrink once the effect is known, and the group can be rotated when a measurement cycle ends.

The same recap made the campaign report say what its equal-spend comparison can show.
The targeted plan maximises the assumed net value and is then scored with it, so it wins by construction; the comparison checks the allocation against its own assumptions, not whether targeting works.
The offer mix follows the same way from the assumed share saved: at the 70 LYD anchor, 2,803 of the 2,954 offers in a 1,000 LYD campaign are the morning pass, the one product assumed to save 10% of churners instead of 5%.

## 44. The experiments are removed, and one note keeps their result

Date: 2026-09-26.

The module carried three experiments beside the product: an LSTM over the monthly steps (T12), synthetic customers from CTGAN and a Gaussian copula (T13), and uplift targeting on two public randomised trials (T17).
Ali removed all three.
This module is one of five parts of the project, the final report has no room for experiments the product does not use, and the teammates' parts cover the syllabus chapters they were for (decision 8).

Removed: `src/prepaid_churn/sequence.py` and the `churn sequence-benchmark` command, `experiments/synthetic.py`, `experiments/uplift.py`, their tests and reports, the `experiments` dependency group with Keras and torch, and tickets T12, T13 and T17.
Decisions 27 to 30 stay as one-line stubs so that their numbers still resolve, and dated records of past checks still say what was true on their day.

What stays is one note in the model selection part of the model card and the brief:

- The LSTM scored a test PR-AUC of 0.2326 against LightGBM's 0.3477, below the logistic regression too, and failed two of the four release checks.
  With two monthly steps the change between months is one subtraction that the engineered features already give LightGBM, so a sequence model has nothing to learn.
- A LightGBM trained on synthetic customers kept at most 45% of the real model's validation PR-AUC with the copula, and 15% with CTGAN.
  The generated customers did not keep the real patterns: a detector told them from real rows at ROC-AUC 1.000.
- The uplift experiment was not a churn model and did not lose to one, so the note leaves it out.
  On a public advertising trial, ranking by uplift beat ranking by risk (Qini 0.0698 against -0.1138), but it needs a randomised campaign with a control group, which this data does not have.
  The permanent holdout of decision 43 is what will provide that data.

Nothing in the product changes: the champion, its reports, the bundle and every other command are as they were.

## 45. The operator is not named

Date: 2026-09-26.

The packages, prices, recharge cards and emergency credit rules in this module come from a real Libyan mobile operator (decision 16).
Ali asked that the instructor learn that the data is real and Libyan, but not which operator it came from.

So the module no longer names it:

- In every document, report, test and screen it is "the operator", or "a Libyan mobile operator" where it is introduced, and its catalogue rows carry the label `Libyan mobile operator`.
- Its Arabic name, its competitor's name and its network code (the MNC) are gone; MCC 606 stays, because it only says Libya.
- Files and commands follow: `data/operator/`, `src/prepaid_churn/operator_market.py`, `churn operator-view`, `reports/operator_view.md` and `docs/operator.md`.
- The customer message starts "Your gift:" instead of the operator's name.

What this does not hide:

- Git history and old commit messages still contain the name; rewriting a shared history would break every teammate's clone, so it is left.
- The antenna module and the root `CODE_REVIEW.md` belong to the team's other parts and still name both Libyan operators, from public tower data.
- The catalogue keeps the operator's own package names, short codes and service names, which someone who knows the Libyan market could recognise.

Nothing about the model, the numbers or the offers changes; only names do.

## 46. Every offer is assumed to keep the same 5% of leavers

Date: 2026-09-26.

T11 assumed that an offer keeps 5% of the customers who would otherwise leave, and that the 1 LYD morning pass keeps 10% (decision 20).
Nothing measured the 10%: it expressed the plan's preference for off-peak bonuses, yet it decided 95% of the offers (2,803 of 2,954 in a 1,000 LYD campaign) and doubled the value the plan claimed.
Ali asked for one share for every offer, with the reason written down.

Why 5%, and the same for every offer:

- No measurement supports a larger effect, or a different one per product; the holdout is what will measure it (decision 43).
- The best-known field experiment with a mobile carrier (Ascarza, 2018, Journal of Marketing Research) found that the customers most at risk are not necessarily the ones an offer changes, so an offer cannot be assumed to keep many of them.
- Vendor case studies report 5% to 12% fewer leavers, but none of them is a controlled experiment.
- A larger share barely changes the plan and mostly inflates the claim.
  On the 30,000 unlabelled customers, with one share for every offer:

| Share for every offer | Offers | Assumed value | Leavers expected to be kept |
|---|---|---|---|
| 5% | 3,643 | 6,186 LYD | 36 |
| 10% | 3,746 | 13,367 LYD | 74 |
| 15% | 3,746 | 20,550 LYD | 111 |
| 20% | 3,746 | 27,733 LYD | 148 |

The offers and their mix hardly move, because the budget decides who is reached, while the claimed value grows with the share.
So the share should be the one we can defend, and 5% is the cautious one.

What changed:

- With one share for every offer, cost is the only thing that separates two offers for the same customer, so each customer gets the cheapest offer that fits them.
- A 1,000 LYD campaign now proposes 3,643 offers, 2,254 of them the morning pass and the rest the 0.5 LYD day pack, for 962.53 LYD: every customer with a positive value is funded, so the budget no longer runs out.
- Its assumed value is 6,186 LYD instead of 11,733; at the same spend, targeting by risk alone is valued at 5,277 LYD and random at 1,012.
- The demo campaign of 1,000 customers and 35 LYD now has 130 offers, 3 of them cut by the budget.
- The mechanism tests keep a larger share for the morning pass, so they still exercise a preference, and a new test checks the shipped policy.

The delivery costs were checked in the same recap and not changed:

- Published averages put operators' operating costs at about 66% of revenue (MTN Consulting, 3Q20), and the cost of delivering 1 GB at about $1 (Dave Burstein, 2021) against a world average price of $2.59 per GB (We Are Social, January 2024), about 40%.
- So the 25% (metered) and 35% (unlimited) shares of price sit inside published averages; a bonus that uses spare off-peak capacity probably costs less, and none of this is the operator's own cost.

If the morning pass should keep an advantage, it belongs in a lower delivery cost for off-peak products, which has a reason behind it, rather than in a larger share kept, which has none.
