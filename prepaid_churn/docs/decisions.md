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
- It is **prepaid**, like the Libyan market (Libyana and Al-Madar), and churn means inactivity, not a cancelled contract.
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
  Almost every later limitation traces back to this line, including the T12 result that a sequence model has nothing to work with over two steps (decision 28).

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

## 23. Emergency credit advice from recharge behaviour, with no repayment model

Date: 2026-09-21.

Ali took T19 as the first experiment after the MVP.
Almadar sells two emergency credit products, both confirmed from the operator's own documents and recorded by T16.
The airtime advance is 1, 3 or 5 LYD, offered when the balance is at or below 0.5 LYD.
The data advance is a flat 5 LYD for 2 GB over 72 hours, offered when the balance is at or below 1 LYD.

`src/prepaid_churn/advance.py` advises a limit and grants nothing.
A limit reaches a customer only if a person approves it, exactly as a retention offer does (decision 14).
No new dependency was added.

There is no repayment model and there will not be one until an operator supplies repayment history (decision 15).
Nothing in the module estimates a probability of repayment, so no figure in the report is a default rate.
`Ali_Branch` also caps by loyalty tier, by a share of customer value, by monthly cumulative exposure and by a chronic-distress screen.
None of those were ported: they need a repayment model, an advance history, a tenure tier or balance-level fields that this data does not contain.
Libyana's Credit Loan, with its tenure gate, grace period and line reset, describes a different operator and is not quoted for Almadar.

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
  The Almadar view is this module's assumption (decision 16), not an operator fact, and the operator's own systems answer it correctly and in real time.
- The emergency credit advice (T19).
  It is a proposal for a person, and no review step exists for it yet; a credit limit needs an approval as much as an offer does (decision 14).
- The review queue.
  A read-only service should not become the place where campaigns are watched; `churn approve` and the demo app own that.

Each one is written in [integration.md](integration.md) with its reason, so a consumer asks instead of building a workaround.

## 27. Keras on the torch backend, and why SDV stays out of this environment

Date: 2026-09-22.

T12 asks for a Keras LSTM and decision 8 puts the syllabus experiments in a separate `experiments` dependency group, so the module a teammate clones stays small.
Both still hold, with one change and one exception.

The change: Keras runs on the torch backend instead of TensorFlow.
T13 needs SDV, SDV needs CTGAN and CTGAN needs torch, so installing TensorFlow as well would put two deep learning runtimes in one repository to run two small experiments.
Keras 3 is the same Keras either way; the LSTM code does not know which backend is under it.

The exception: SDV is not in the group.
It caps pandas below 3, and adding it to the lock downgraded pandas from 3.0.5 to 2.3.3 for the whole project, including the default environment.
That is not a small thing here: the frozen bundle records the library versions it was built with and refuses to load under different ones (T8), so the downgrade broke `churn score`, `churn decide` and the service in one command.
The module stays on pandas 3, and T13 runs in its own environment (decision 28).

So `uv sync` installs what it always did, `uv sync --group experiments` adds Keras and torch for T12, and neither touches the versions the champion was frozen with.
A run of the full pipeline after the group was added reproduced bundle `lightgbm-2026-09-19-ef9430fb` and every committed report unchanged.

## 28. The LSTM loses, and that is the T12 result

Date: 2026-09-22.

The benchmark ran once on the frozen test window, calibrated the same way as T7 and scored with the same metrics: PR-AUC 0.2326 against LightGBM's 0.3477 and the logistic regression baseline's 0.2770, capture at 10% of 0.4941 against 0.6152.
It fails two of the four success thresholds of decision 13 and would not be released.

This is the expected answer and it is worth stating plainly rather than tuning until it looks better.
A window here is two monthly steps.
The movement between two points is a subtraction, the T5 features hand that subtraction to LightGBM directly, and the LSTM has to learn it from two steps and about 400 churners in the training split.
A recurrent layer earns its place when there is a history to remember, and two steps is not a history.

What was deliberately not done: no architecture search, no threshold moved, no second look at the test window.
The architecture, the epochs and the calibrator were chosen on validation customers, and the frozen champion was not retrained or reconsidered (decision 6).
Tuning an experiment against the test set until it beats the champion is exactly the mistake the split design exists to prevent, and the grade for this chapter does not depend on the LSTM winning.

`Ali_Branch` reached the same conclusion from the other side: its API once returned an `lstm_churn_probability` beside the main score, and its own integration document records that the field and the benchmark arm were removed because "M1 is a single gradient-boosting model family now".
Two independent efforts on this data dropped the recurrent model for the same reason.

The honest caveat travels with the result in [../reports/sequence_benchmark.md](../reports/sequence_benchmark.md): with six or twelve months per customer, or with call-detail records instead of monthly totals, the comparison is worth running again.

## 29. A synthetic copy is a demo, not a way to share customer data

Date: 2026-09-22.

T13 asked the operator's question rather than the model's: real prepaid data cannot leave a telecom operator, so can the operator fit a generator on its customers, hand out the copy, and still let someone build a model worth having?
The experiment fits CTGAN and a Gaussian copula on 6,000 real training customers and 28 features, then trains the same LightGBM on each copy and scores all of them on the same real validation customers.

The answer on this data, at this budget, is no.
A model trained on the copula copy keeps 45% of the PR-AUC that the same model reaches on real customers, and the CTGAN copy keeps 15%.
Both copies are told apart from real rows with a detection ROC-AUC of 1.000, so neither is realistic enough to be mistaken for the real thing either.
CTGAN also lost the churn rate itself: 16.8% of its rows are churners against 4.7% in the real sample, and a model trained on the wrong base rate is wrong before it has learnt anything.

Two results are worth keeping beyond the grade.

The Gaussian copula, which is the simple baseline the GAN has to beat, beat it on every measure that matters here.
That is a normal outcome for 60 epochs on a laptop CPU and it is reported as it came out.
A longer fit would probably close the gap, and the report says so rather than presenting a budget as a ceiling.

The business view is where the copies visibly came apart.
Shown in Almadar terms through T18, 72% of the real customers are on pay-as-you-go, 14% hold a monthly bundle and 14% buy daily packs.
The copula copy puts 86% on daily packs and nobody on pay-as-you-go; CTGAN puts 44% on monthly bundles.
Every column in those copies is individually inside its real range, and the customers are still on the wrong packages, which is the failure a column-by-column quality score does not show.

This is also the measured version of an argument this module already made twice.
Decision 7 cut the generated population from the CVM proposal and decision 15 declined to carry `Ali_Branch`'s hazard-formula labels, both on the grounds that a model fitted to generated data is evidence about the generator and not about customers.
T13 puts a number on it on our own data.
So the rule stands and now has a citation: no synthetic row trains, calibrates or evaluates anything in this module, and no report or presentation may describe this module as producing a shareable synthetic customer base.

What the copies are good for, and how this module uses them: a demo with no real customers in it, a schema to build a pipeline against, and a load test.
That is real value and it is what the report claims.

What was not measured, and would have to be before any copy left an operator: privacy.
A copy can pass every fidelity test and still memorise a rare customer, and membership inference is the test for that, not column shapes.

One honest note on method.
The first version of the fidelity check counted rows with a negative amount and reported about 54% for both copies.
That check was wrong: `diff_*` columns are differences and are negative for half the real customers too, so the same check called the real data 58% impossible.
It was replaced with a comparison against the columns that are never negative in the real sample, where both copies score 0%, because SDV keeps each column inside the range it learnt.
The wrong version is recorded here because it is the kind of check that looks like a finding and is really a bug.

## 30. Risk targeting and uplift targeting are not the same ranking

Date: 2026-09-22.

T11 gives a bonus to the customers this module ranks riskiest and assumes a share of them are saved by it.
That assumption is the weakest number in the module, and the upGrad data cannot test it: it has no treatment arm, so no uplift model can be fitted on it at all.
T17 therefore measures the method on two public randomised trials and carries back the lesson, not the numbers.

On Criteo's 1.4 million randomised rows, ranking by uplift reaches a Qini of 0.0698 while ranking by predicted response, which is the ranking T11 uses, reaches -0.1138.
Twenty uninformative rankings on the same rows span plus or minus 0.0110, so the uplift ranking clears the noise and the response ranking is not merely worse, it is worse than random.
The realised uplift in the top 30% is +2.89% against +0.02%.
The people most likely to respond were not the people the advertisement moved, and there is no reason to expect churn to behave differently.

Orange Belgium, the telecom dataset, answers nothing, and that is reported rather than dressed up.
Its held-out 30% holds 3,569 customers and 120 churners, and every ranking, including the random one, sits inside the same noise band.
A dataset of that size cannot estimate an uplift ranking, and the honest output of the run is that sentence.
This is worth keeping because the SIC action plan lists Orange Belgium as a churn-uplift source: it is the right industry and the right action, and it is still too small to settle anything.

What this changes in the module: nothing in the code, and one sentence in how T11 must be read.
The riskiest decile is not the persuadable decile, so "share saved" stays an assumption with a stated value rather than a measured rate, and every LYD figure downstream of it stays a scenario.
T11's random holdout of proposed customers is the only instrument this module has for turning that assumption into a measurement, and it only pays once a real campaign runs against it.
That holdout was already in T11 before this experiment; T17 is the reason to keep it when someone asks why part of the budget is not spent.

Two smaller decisions recorded here.

The Qini implementation is ported by hand from `Ali_Branch` rather than imported from scikit-uplift, keeping both things his comments say are easy to get wrong: the control arm is rescaled to the treated arm's size at every depth, and the coefficient is normalised by the perfect ranking.
It is then checked against `sklift.metrics.qini_auc_score` at runtime, and the agreement is printed in the report: 8.14e-06 on Criteo and 1.46e-03 on the small Orange holdout.
An implementation that is only a call to the thing it is checked against cannot disagree with it, which is his argument and it is right.

Orange's outcome is flipped on purpose.
Its label is churn, so a call that works makes the label smaller, and an uplift model fitted on churn ranks the customers a call would lose.
Retention is the response the campaign is trying to produce, and getting that sign wrong is the classic way an uplift study reports its best customers as its worst.

The two datasets are downloaded on demand into `data/external/`, which is git-ignored.
Both are under non-commercial licences and neither is ours to redistribute, so unlike the Kaggle data in `data/raw/` (decision 9) they are never committed.

## 31. The Mix families leave the catalogue, and a removal is recorded rather than silent

Date: 2026-09-22.

Ali confirmed that Almadar no longer sells the five Mix families, answering the question T16 left open on 2026-09-19.
He had removed the same 20 packages from his own catalogue on 2026-09-18 in commit `62040af`, which showed the removal was deliberate but never recorded a reason.
The catalogue now holds 37 packages in 12 families, which is exactly what `Ali_Branch` held, so the difference T16 pinned with a test is closed.

Deleting the rows alone was not acceptable.
The files in `data/almadar/source/` are byte-for-byte copies of the operator's own export (port step 1), and `check_against_source` required every row in them to appear in the catalogue exactly once.
Editing the source file to match would have destroyed the evidence, and relaxing the check would have allowed any package to disappear unnoticed, which is precisely how the Mix question arose.

So a removal is now recorded.
`data/almadar/excluded.csv` holds one row per package that the operator file lists but the operator no longer sells, each with its source row, a reason, the person who decided and the date.
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
