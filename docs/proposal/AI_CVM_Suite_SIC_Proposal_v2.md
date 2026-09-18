# AI Customer Value Management (CVM)

### Component 3 of the Telecom AI Platform — Samsung Innovation Campus, Libya AI 2026

| | |
|---|---|
| **Component** | Customer Intelligence, Retention & Loyalty |
| **Operator** | Almadar Aljadid — المدار الجديد (MCC/MNC 606-01) |
| **Repository** | `ali_branch` |
| **Duration** | 3 weeks |
| **Infrastructure** | CPU-only; free-tier GPU for one module. Budget ≤ $20 |

---

## 1. The Problem

Almadar's market is overwhelmingly **prepaid**, which removes everything a
conventional retention system is built on. No contract, no billing
relationship, no cancellation event. A customer does not leave — they stop
topping up, and the revenue disappears without a single event being logged.

Four consequences shape the whole design.

**Churn is an absence, not an event.** There is nothing to react to, only a
decaying signal nobody watches per-subscriber. The target has to be
constructed: *zero revenue-generating events for 30 consecutive days*.

**Dual-SIM is the norm, not a segment.** At the penetration levels in this
market, "active" is close to meaningless. A subscriber can stay technically
active while most of their spend has moved to the other SIM. The leading
indicator is measurable and currently unmeasured: **incoming call volume
holding steady while outgoing volume and off-net share both rise** — that
subscriber has quietly made this their *receiving* SIM.

**Blanket campaigns waste most of their budget.** A large share of any
untargeted incentive lands on subscribers who would have stayed anyway, and
another share on subscribers already gone. Without a control group, net impact
is never isolated, so nobody can prove the campaign did anything.

**Some retention actions cause churn.** Almadar's emergency data advance costs
5 LYD. The smallest recharge card sold is 3 LYD. A subscriber whose habitual
top-up is the smallest card **cannot clear that debt in one transaction** — and
because re-subscription requires it cleared, they are locked out of the service
they reached for. §2.5 develops this.

---

## 2. The Pipeline

The whole component is one decision, built in four steps:

```
   predict churn  ──►  understand value  ──►  estimate treatment effect  ──►  decide
        M1                   M2                        M3                  Decision
                                                                            Engine
```

Each step answers a question the next one needs. The last step is where the
money is, and **"no action" is a first-class outcome** — for most subscribers
it is the correct one.

| | Module | Question | Code |
|---|---|---|---|
| **M1** | Silent Churn Engine | Who is leaving, and *when*? | `models/m1_churn/` |
| **M2** | Value & Loyalty Tiering | What are they worth? | `models/m2_value/` |
| **M3** | Uplift Engine | Who can actually be **influenced**? | `models/m3_uplift/` |
| — | **Decision Engine** | Is intervening **worthwhile**? Which action? | `decision/` |
| **M4** | Smart Advance | How much credit can we safely extend? | `models/m4_advance/` |

### 2.1 M1 — Predict churn

Structured as an experiment rather than a single model, because the experiment
is more informative than either arm alone.

| Arm | Input | Method |
|---|---|---|
| **A** | ~80 engineered features | LightGBM primary; XGBoost and CatBoost challengers; Decision Tree, Logistic Regression, Naïve Bayes, KNN and SVM reported as baselines |
| **B** | Raw 90 × *k* daily tensors | LSTM: Masking → LSTM(64) → Dropout(0.3) → LSTM(32) → Dense. **No hand aggregation** |

Shared framing: **90-day observation → 15-day gap → 30-day outcome**, temporal
split, class weighting first with SMOTE/ADASYN as a documented comparison
applied inside CV folds. Both arms isotonic-calibrated, because the decision
engine consumes probabilities as monetary expectations — a 0.31 must mean 31%.

**Metrics:** PR-AUC (primary), lift @ deciles 1–3, Brier, ROC-AUC. **Accuracy
is not reported** — meaningless at a low base rate, and CI fails if it appears
as a headline.

**Either outcome is a result.** If LightGBM wins — likely, on short sparse
prepaid histories — we explain why: 90 timesteps of mostly-zero activity is a
weak sequence signal, and the engineered decay ratios already encode most of
the temporal information. Demonstrating an informed architecture choice beats
defaulting to a neural network because it sounds advanced.

**M1b — time-to-churn.** Cox Proportional Hazards with a Random Survival Forest
challenger. Classification answers *if*; survival answers *when*. Intervening
40 days early wastes budget; 5 days late wastes everything. The hazard
inflection points set the retention-ladder stage boundaries.

**Explainability:** SHAP on Arm A, surfaced in plain language — *"has not
topped up in 23 days"*, not a feature name and a coefficient — and aggregated
to feature-family level, because eighty individual contributions are not
legible to an analyst.

### 2.2 M2 — Understand value

Three unsupervised techniques in parallel, plus a business-legible reference:
**K-Means** on scaled RFM-LE (*k* by silhouette and elbow), **hierarchical
clustering** with a dendrogram as a structural cross-check, **PCA** for 2-D
visualisation, and **rule-based RFM-LE quintiles**. Where the rules and the
clusters disagree, the disagreement is itself a dashboard insight.

**RFM redefined for prepaid**, because textbook RFM assumes purchase
transactions and prepaid has none:

| Dim | Our definition |
|---|---|
| **R** | Days since last **revenue-generating** event. Usage alone does not count — burning residual credit generates no revenue |
| **F** | Recharge count in 90d, **penalised by gap volatility**. Five regular recharges beat five erratic ones |
| **M** | Total LYD in 90d **plus the 30d-vs-prior-60d slope**, so decline is visible inside the score |
| **L** | *(added)* tenure + consecutive active months + lifetime spend percentile |
| **E** | *(added)* service breadth across voice, SMS, data, bundles, transfers, advances |

**CLV:** BG/NBD + Gamma-Gamma, treating each **recharge as a transaction**. The
non-contractual, alive-or-dead-unobserved assumption behind BG/NBD is literally
true in prepaid — an unusually clean fit rather than a borrowed one. Validated
on UCI Online Retail II before being pointed at recharges.

**CLV's real job is as the budget ceiling.** Total retention spend on a
subscriber never exceeds a configurable fraction of predicted 12-month CLV
(default 15%). That single constraint is what makes the engine defensible to a
CFO.

### 2.3 M3 — Estimate treatment effect

**This is the step that decides where money goes.** A churn score ranks who is
*at risk*; an uplift score ranks who is *movable*. Those are different
populations, and targeting on churn probability alone systematically funds the
wrong subscribers.

| Quadrant | Behaviour | Treat? |
|---|---|---|
| **Persuadable** | Stays only if treated | ✅ the entire target |
| Sure thing | Stays either way | ❌ pure waste |
| Lost cause | Leaves either way | ❌ pure waste |
| **Sleeping dog** | Leaves **because** treated | ❌ actively harmful |

The sleeping-dog quadrant is why this module cannot be skipped. Contacting a
dormant-but-not-departing subscriber can remind them to leave, so a system
without an uplift model does not merely waste budget — **it causes churn it
would not otherwise have caused.**

**Method:** two-model difference (treated response minus control response). Not
a causal-inference library: at this data scale the extra machinery buys
precision we could not validate anyway, and the simpler method is defensible in
a three-minute pitch. Recorded as a decision, not an omission.

**Validated on real randomised data.** The method is trained and evaluated on
**Criteo's 25M-row incrementality test** — genuine randomised treatment and
control arms — before it is applied to the generated population. That converts
*"our uplift model scores well on data we made up"* into *"our uplift method is
validated on 25M real randomised rows, then applied to a Libyan population"*.

Evaluated on Qini coefficient and uplift@k, not accuracy — there is no
ground-truth uplift for any individual, since you never observe both outcomes
for the same person.

**A mandatory 10% randomised holdout** runs on every campaign. Without it,
every ROI figure in §6 is an assertion rather than a measurement.

### 2.4 The Decision Engine — decide whether to intervene

Two questions, in order.

**First: is intervening worthwhile at all?**

```
E[gain] = uplift × CLV − offer_cost
```

A positive value means treating is worthwhile before guardrails; a negative one
means it is not, **regardless of how high the churn score is**. Most
subscribers should come out of this step with no action.

**Second: if yes, which action?**

The action space is the operator's **real catalogue** — 37 published bundles
plus "no action". This matters for two reasons that are not about merchandising:

- **Executability.** *"Give this subscriber 4.2 LYD of value"* is unfalsifiable
  and cannot be actioned. *"Offer نت 20 at 10% off"* is both.
- **Honest economics.** An invented offer has an invented cost, which would
  make the margin floor enforce one made-up number against another. Real prices
  are what keep the guardrails meaningful.

Price for bundle *b*, subscriber *i*:

```
P(i,b) = P_base(b) × (1 − d(i,b))

d(i,b) = clip( w₁·ChurnRisk + w₂·Loyalty + w₃·PriceSensitivity
             − w₄·AffordabilityHeadroom , 0 , d_max(tier) )
```

with `d_max` rising 5% → 20% across Bronze, Silver, Gold and Platinum.

**Six guardrails, enforced in code and asserted in required CI gates:**

| | Guardrail |
|---|---|
| 1 | **Margin floor** — never price below variable cost plus minimum margin |
| 2 | **CLV ceiling** — cumulative 12-month spend ≤ 15% of CLV, checked against *trailing* spend. Twelve individually-reasonable offers is how this gets defeated |
| 3 | **Budget** — cohort allocation as a knapsack/LP maximising expected retained margin |
| 4 | **Cannibalisation** — see below; the one that matters most here |
| 5 | **Fairness** — no protected or proxy-protected attributes in pricing, plus a distribution audit across value deciles and tenure bands |
| 6 | **Auditability** — every decision logs inputs, weights, binding constraints and reason codes, replayable on demand |

Guardrails **re-check the final number** rather than trusting the pricing
function to have applied them. A breach raises; it does not clamp silently.

**Off-peak offloading.** Almadar sells a **1 LYD pass for unlimited data *and*
voice, valid 06:00–11:00**. That tells us the operator has already identified
and priced its own spare capacity, and exactly when it is — so this is the
personalisation of an existing product rather than the proposal of a new one.

It is also the cheapest retention instrument on the price sheet, which is why
the engine reaches for it before any price cut. Value-add before discount: a
headline cut permanently reduces realised ARPU and is trivially matched; an
off-peak grant is perceived as generous and leaves the price sheet intact.

**But it is cheap enough to be dangerous**, and §6.2 quantifies exactly how.

**The retention ladder** is a delivery policy over M1b and the engine, not a
separate module. Stage boundaries come from the hazard curve rather than
intuition, and spend follows an **inverted U** — low, then high, then low
again — because recovery probability collapses faster than offer value rises.
Most operators escalate as the line gets colder, which is backwards.

### 2.5 M4 — Smart Advance

Almadar runs two emergency-credit products:

| | **رصيد في وقته** (airtime) | **نت في وقته** (data) |
|---|---|---|
| Access | `*140#` | `*000#` |
| Amount | **1 / 3 / 5 LYD** | **flat 5 LYD** (2 GB, 3 days) |
| Eligibility | balance **≤ 0.5 LYD** | balance **≤ 1 LYD** and quota **< 250 MB** |
| Allocation | *"according to consumption"* | none — identical for everyone |
| Settlement | at first recharge | at first recharge |

Neither is a new product. What neither has is a risk model, and four things
follow:

**Eligibility is the inverse of a risk filter.** Both gate on the subscriber
being nearly out of money, so the eligible population is by construction the
one least able to repay.

**"According to consumption" is not a risk model.** Consumption is not
repayment probability. A heavy user in decline consumes a great deal and repays
badly; the rule cannot tell them apart from a heavy user who is fine.

**The data advance has no differentiation at all.** Five dinars for everyone.

**And the debt can exceed what one transaction can clear.** Smallest card 3 LYD,
data advance 5 LYD. The debt persists, re-subscription requires it cleared, and
the subscriber is locked out of the service they reached for. The two products
being mutually exclusive compounds it — subscribers in difficulty **alternate
between them**, a clean measurable distress signal nobody is watching.

**Our design:**

```
Limit(i) = min( f(PD), g(tier), h(CLV), affordability(i) )
```

Two PD heads sharing M1's feature pipeline — not separate infrastructure, which
is why M4 is cheap to build despite being the most differentiated idea here.
Target: settled by the next recharge, censored at 14 days (behavioural, since
neither product publishes a grace period).

**`affordability` is the term the incumbent has no equivalent of.** It uses the
subscriber's **modal** recharge, not their mean — the mean is inflated by a
single salary-week top-up they will not repeat, and using it would
systematically over-lend to exactly the subscribers this guard protects.

Mandatory guards: affordability ceiling, chronic-distress exclusion (including
product alternation), cooling-off, CLV-bounded exposure, lockout-risk flagging,
and an **affordable fallback** — declining with nothing sends the subscriber
away; declining with the 0.5 LYD pack they *can* afford is a service.

The objective function is **subscriber solvency, not recovery yield.**

---

## 3. Data

### 3.1 Datasets

| | Dataset | Size | Role |
|---|---|---|---|
| **A** | UCI Iranian Churn (563) | 3,150 | **Primary.** Prepaid, MENA, carries a service-quality feature most churn datasets omit, and a 9-month/3-month framing that matches a real campaign |
| **B** | Cell2Cell (Duke/Teradata) | 100,000 × 2 files | Scale, and **measured distributions** for our two signature features |
| **C** | IBM Telco | 7,043 | Independent CLTV benchmark; fast first baseline |
| **F** | Criteo Uplift | 25M | **Real randomised treatment/control.** Validates the M3 method |
| **G** | Hillstrom | 64,000 | Uplift warm-up; clearest demonstration of the four quadrants |
| **H** | KKBox WSDM | ~1M | Real *daily* sequences; churn defined as non-renewal — an absence, like ours |
| **J** | UCI Online Retail II | 1.07M | BG/NBD validation before CLV touches recharges |

**Dataset A** needs two corrections: ~300 duplicate rows (~9.5%) deduplicated,
and the pre-computed `Customer Value` field dropped because it partially
encodes the outcome. Both are why our metrics sit below published figures.

**Dataset B grounds the two features the project is built on.** It is the
original two-file Duke distribution rather than a condensed cut, so it keeps
placed and received voice as separate columns, and peak and off-peak minutes as
separate columns:

| Feature | Measured |
|---|---|
| `incoming_outgoing_ratio` | median 0.280, p10 0.052, p90 0.681 |
| `offpeak_data_ratio` | median off-peak share 0.424 |
| `revenue_decay_ratio` | median 1.012, **46.8% declining** |

Both leakage columns are 0% null across all 100,000 rows.

> **Three caveats travel with it.** The label is balanced at ~49.6% churn, so
> the prevalence is unusable — calibrating on it would calibrate to a 50% prior
> and destroy the claim that a 0.31 means 31%. The leakage ratio **does not
> predict churn in this data** (0.282 vs 0.278), which is expected in a
> single-SIM postpaid market: the source grounds the feature's *distribution*,
> not its *predictive power*. And 22 columns of US household marketing data —
> ethnicity, marital status, income, child-age brackets — are dropped at the
> **ingestion boundary**, not merely excluded from pricing, because several are
> protected attributes and a Libyan prepaid operator holds none of it.

### 3.2 The operator's commercial layer

Prices, volumes, recharge denominations and tariffs are transcribed from
Almadar's published material into `conf/catalogue.yaml` and `conf/market.yaml`.
They serve two specific purposes — **the action space** the decision engine
selects from, and **the cost model** the margin floor enforces against.

| | |
|---|---|
| Recharge ladder | **3, 5, 10, 20, 40, 100 LYD** |
| Catalogue | **37 bundles across 12 families**, from 0.5 LYD daily packs to 400 LYD 5G monthlies |
| Off-peak product | عروض الصبح — 1 LYD, unlimited data + voice, **06:00–11:00** |
| On-net voice | **0.090 LYD for the first 3 minutes**, then 0.050/min |
| Off-net / landline | 0.090 / 0.040 per minute |
| SMS | 0.050 **both directions** — no on-net discount |
| PAYG data (Bjawak) | 0.025/MB ≈ **25× the bundle rate** |

Three of these change how the pipeline works:

**On-net voice is a block tariff, not a rate.** A 1-minute call costs 0.090
LYD; a 10-minute call costs 0.044/minute. Call *length* drives revenue, so
generated call lengths must be realistic.

**No on-net SMS discount** means SMS carries no competitive signal. Any leakage
feature built on SMS mix would be noise, and the feature config excludes it by
name with the reason recorded.

**PAYG data at ~25× the bundle rate** makes `bundle_vs_payg_share` a targeting
feature rather than a ratio: a subscriber paying PAYG is either **unaware** of
the catalogue or **unable to afford** a bundle up front. Different problems,
different interventions.

Every value carries a status of `confirmed`, `assumption` or `placeholder`, and
`docs/MARKET_QUESTIONS.md` tracks which is which. Bundle `variable_cost` is an
**estimate** (25% of price for metered, 35% for unlimited) and is labelled as
one everywhere it appears.

### 3.3 The generated population

No public Libyan CDR dataset exists, and none should — subscriber data cannot
legally or ethically leave an operator. A conditional tabular GAN generates the
population conditioned on the real features so joint structure is preserved:
CTGAN primary, TVAE challenger, Gaussian copula baseline, with the three-way
comparison reported.

**Where a real distribution exists, the overlays fit against it** rather than
inventing a shape. The leakage ratio, off-peak share and decay ratio all have
measured baselines from Dataset B; the generator reproduces that shape and
applies the Libyan deviation on top — a fatter dual-SIM right tail, a
06:00–11:00 concentration, the recharge ladder. Fitting to a measured baseline
and documenting the deviation is a materially stronger position than generating
blind.

**Quality gate:** KS-complement ≥ 0.85, pairwise correlation delta ≤ 0.10, and
a **discriminator detection test** — a LightGBM classifier trained to separate
real from synthetic must not exceed 0.65 AUC. Above that the generator is
rejected and retrained. *The GAN is evaluated with an adversarial test, the same
principle that trains it.*

**Generated-population metrics are not evidence of production performance.** The
deliverable is a validated pipeline and decision logic, priced against a real
catalogue.

### 3.4 Leakage controls

Three invariants, each a required CI gate.

1. **Point-in-time correctness.** Features end strictly before the label window
   opens.
2. **Temporal splits, never random.** There is deliberately no `random_split`
   function anywhere, and a test asserts its continued absence.
3. **Label artefacts excluded; label drivers retained.** This distinction
   breaks the project in opposite directions if confused, so it is explicit in
   code:
   - **Artefacts** — `hazard_score`, `churn_date`, the label itself — must
     never reach the feature matrix. Any one lets a model reconstruct the
     outcome, producing a model that scores beautifully and knows nothing.
   - **Drivers** — the behavioural fields the hazard is a function of —
     **remain available**. The hazard is built from observable behaviour
     precisely so the signal is recoverable. A model that can see no driver of
     its own label has nothing to learn, and every metric collapses for a
     reason that is extremely hard to trace.

   The tests assert **both** directions, so a well-intentioned tightening of
   leakage control cannot silently gut the feature set.

---

## 4. Architecture

Four containers, CPU-only at serving time, under 3 GB RAM. One module trains on
a free GPU session and ships as a saved artefact.

```
  SOURCES      UCI Iranian · Cell2Cell · IBM Telco · Criteo · Hillstrom · KKBox
                                    +
               Almadar catalogue, tariffs, recharge ladder  (conf/)
                                    ▼
  INGEST       Pandera contracts · dedup · MSISDN → SHA-256 · → Parquet
                                    ▼
  SYNTHESIS    CTGAN ⇄ discriminator · overlays fitted to measured baselines
               [ GATE: KS ≥ 0.85 · corr Δ ≤ 0.10 · detection AUC ≤ 0.65 ]
                                    ▼
  FEATURES     rolling 7/30/90d · RFM-LE · decay · leakage · weekly rhythm
               (DuckDB)      features_offline · sequences_offline · online store
                                    ▼
  MODELS       M1 churn (LightGBM vs LSTM + Cox)    M2 value + CLV
               M3 uplift (validated on Criteo)      M4 repayment PD
                                    ▼                    [ MLflow ]
  DECISION     E[gain] = uplift × CLV − cost    →    worthwhile?
               action from the real catalogue   →    which offer, or none
               GUARDRAILS: margin · CLV ceiling · budget · cannibalisation ·
                           fairness · decision log
                                    ▼
  API          /v1/cohort/query  /v1/score/churn  /v1/offer/next-best
               /v1/price/quote   /v1/advance/limit  /v1/subscriber/{id}
                                    ▼
  SURFACES     Command Center · Channel Simulator   │  Components 4 & 5
                                                    │  consume read-only
```

There is **no agent container**, which is the strongest available enforcement
of "no LLM in a path that moves money" — the path does not exist.

Full layer map: `docs/architecture.md`. Field-by-field spec:
`docs/data_dictionary.md`.

---

## 5. Deliverables & Stack

### Interfaces

**Command Center** (Streamlit, four screens): Executive Overview · Segment
Explorer · **Subscriber 360** — one hashed ID to churn probability from both
arms, survival curve, RFM-LE, CLV, SHAP in plain language, recommended action
*with the constraint that set it* · **Campaign Builder**, which shows **which
guardrail bound and how many candidates each rejected** — the most persuasive
thing on screen.

**Channel Simulator**: USSD (`*140#`, `*000#`) and SMS previews in Modern
Standard Arabic with RTL rendering. Arabic SMS is UCS-2 — 70 characters, not
160 — so copy that fits in English silently becomes two messages; the simulator
enforces the real limit.

**API**: FastAPI, Pydantic v2, p95 < 200 ms on one CPU container. Identifiers
are salted SHA-256 throughout; a raw MSISDN returns 422. `/health` reports `ok`
only when every model is loaded.

### Deliverables

| | |
|---|---|
| D1 | `docker compose up` reproduces the system from a clean clone |
| D2 | Synthesis engine passing the SDMetrics gate, three-way generator comparison |
| D3 | M1 benchmark: calibration curves, PR-AUC, lift, written architecture verdict |
| D4 | **M3 uplift validated on Criteo's real randomised arms** before application |
| D5 | All models logged in MLflow with params, metrics and artefacts |
| D6 | API with live Swagger docs and p95 latency evidence |
| D7 | Command Center + Channel Simulator functional on generated data |
| D8 | Model cards, data dictionary, market-facts register |
| D9 | Integration contract with a worked example |
| D10 | Technical report (~20 pp) + 3-minute deck + 5-minute demo video |

### Stack

Python 3.11 · pandas/Polars · DuckDB · Pandera · SDV (CTGAN/TVAE/Copula) ·
scikit-learn · LightGBM/XGBoost/CatBoost · lifelines · lifetimes ·
scikit-uplift · SHAP · Optuna · PuLP · TensorFlow (LSTM only) · FastAPI ·
Streamlit · MLflow · Evidently · pytest · GitHub Actions · Docker.

No agent framework, no vector store, no transformers. Compute: Oracle Cloud
Always Free for the demo host, Colab free T4 for the LSTM. **Total $0–20.**

---

## 6. Business Case

Illustrative, built on stated assumptions, shipped as a spreadsheet so any
input can be changed. The method is the point.

**Assumptions:** 1,000,000 addressable prepaid · 30 LYD ARPU · 3.5% monthly
silent churn (~35,000) · 120,000 treated per campaign · 10% control · 1.5 LYD
blended incentive.

### 6.1 Retention campaign

| | |
|---|---|
| Monthly revenue at risk | 35,000 × 30 = **1,050,000 LYD** |
| Uplift 2.5 pp on 120,000 treated | **3,000 additional retained** |
| Retained value, 12-month horizon | **1,080,000 LYD** |
| Campaign cost @ 1.5 LYD | **180,000 LYD** |
| **Net** | **900,000 LYD · ROI ≈ 6.0×** |

| ROI | Cost 1.0 | Cost 1.5 | Cost 3.0 |
|---|---|---|---|
| **Uplift 1.0 pp** | 3.6× | 2.4× | 1.2× |
| **Uplift 2.5 pp** | 9.0× | 6.0× | 3.0× |
| **Uplift 4.0 pp** | 14.4× | 9.6× | 4.8× |

**There is no loss-making cell, and that is not the reassurance it looks like.**
At 30 LYD ARPU against a 1–3 LYD instrument the incentive arithmetic is simply
robust. Presenting this table as the main risk would be flattering the
proposal. The real fragility is next.

### 6.2 Cannibalisation — the constraint that actually binds

The morning pass is 1 LYD. The monthly ladder runs 20–80 LYD, with the mid-tier
نت 20 at **35 LYD for 20 GB**. If the pass persuades a heavy user to stop buying
a monthly bundle, the ARPU loss dwarfs the incentive saving.

| | |
|---|---|
| Monthly retained value | 90,000 LYD |
| ARPU lost per downgrader off a 35 LYD monthly | 34 LYD/month |
| Downgraders that erase the entire gain | ≈ **2,650** |
| As a share of the treated cohort | **≈ 2.2%** |

**Above roughly 2.2% cannibalisation the whole retention gain disappears.**

And it cannot be escaped by assuming a richer base. The break-even is

```
share ≈ uplift × ARPU / (bundle − 1)
```

so when the bundle tracks ARPU — as it must, for internal consistency — the
ARPU terms cancel and **break-even ≈ the uplift itself**, flat at ~2.5%
regardless of whether ARPU is 30 or 80. Raising ARPU inflates both sides.

The only real levers are **uplift** (which is why M3 is validated on real
randomised data) and **the size of the concession**. This is why the
cannibalisation guard, not the margin floor, is the guardrail that matters most
here, and why the simulated ARPU-erosion cap sits at **2%** — just below
break-even, in code, before any cohort ships.

### 6.3 Avoided waste

A blanket campaign across the full base at the same incentive costs
**1,500,000 LYD/month** for comparable or worse uplift. Targeted selection saves
roughly **1,320,000 LYD/month**. In prepaid CVM, *not* spending is usually worth
more than spending better.

### 6.4 Prevented lockouts

Every step is a labelled assumption; the chain is the point.

| | |
|---|---|
| Monthly emergency-credit users | ~150,000 |
| Of which the 5 LYD data advance | ~50,000 |
| Share whose modal recharge is the 3 LYD card | ~26% → **13,000 unclearable** |
| Persisting to lockout → churning within 90 days | → **780 subscribers** |
| Remaining 12-month value each | 360 LYD |
| **Monthly loss** | **~281,000 LYD** |
| **Avoidable by declining with an affordable fallback (~60%)** | **~168,000 LYD/month** |

Harm the operator's reporting cannot see, because it records the debt as
outstanding rather than the subscriber as excluded. Also the cheapest thing here
to fix: the facility, billing integration and recovery mechanics already exist.
**Only the limit-setting logic changes.**

---

## 7. Plan & Risks

| Week | Goal |
|---|---|
| **1** | Data flowing, schema and API contracts frozen, CTGAN passing its gate, LightGBM baseline with honest temporal-split metrics |
| **2** | M1 both arms + calibration · M2 clustering + CLV validated on Online Retail II · **M3 validated on Criteo** · M4 both PD heads · decision engine with all six guardrails. **Day-10 feature freeze** |
| **3** | Campaign Builder · channel simulator · contract test with the consuming components · latency + drift · documentation · demo video · three timed dry-runs |

**Descope in this order:** KKBox → hierarchical clustering → RSF challenger →
Optuna → Evidently.

**Never cut:** the M1 benchmark, calibration, the M3 uplift validation, the six
guardrails, the M4 safety guards, the control holdout, the leakage gate, the
honest-metrics disclosure.

| Risk | Mitigation |
|---|---|
| Generated data too clean, models look unrealistically good | Discriminator detection gate; deliberate noise injection; naive and honest metrics both reported |
| Inflated metrics from duplicates or leaky features | Leakage CI gate; temporal splits; artefacts and drivers separated explicitly and tested both ways |
| Cannibalisation swamps the gain | Quantified in §6.2; simulated margin check before cohort approval; erosion cap below break-even |
| Cost estimates wrong, margins mislead | Labelled as estimates everywhere; margin reported as a ratio against a stated assumption |
| Integration failure in week 3 | Contracts frozen day 3; stub endpoints day 5; contract test day 12 |
| Live demo failure | Pre-recorded video; local Docker fallback; no venue Wi-Fi dependency |

### Ethics

No real subscriber data; SHA-256 + salt from ingestion, with CI scanning for
MSISDN patterns. Credit optimises for **solvency, not recovery yield**, and
declining comes with an affordable alternative. No protected attributes in
pricing, audited post-hoc. No LLM in any decision path. Every decision logged
and replayable, with a human-readable reason on every offer. And every
commercial estimate is labelled as an estimate.

---

## 8. Pitch

**① The pipeline is the product, not the churn score.**
Predict → value → **treatment effect** → decide. Most churn projects stop at
step one and target everyone at risk. We target only the *persuadable*, exclude
the *sleeping dogs* — subscribers who leave **because** you contacted them —
and validate the uplift method on 25 million rows of real randomised data
before it touches ours.

**② We found a harm the operator's reporting cannot see.**
The data advance costs 5 LYD. The smallest recharge card is 3 LYD. If that is
the card you buy, you can never clear the debt in one transaction — and until
you do, you are locked out of the service you reached for. Both credit products
gate on the subscriber being nearly out of money and allocate by "consumption"
rather than repayment probability. ~168,000 LYD a month, from logic changes
alone.

**③ We know exactly where our own idea breaks.**
The operator sells a 1 LYD unlimited morning pass, so off-peak offloading
personalises a product that already exists. It is also cheap enough to
cannibalise a 35 LYD monthly bundle — and we can show that **above 2.2%
downgrade rate the entire gain disappears**, that raising ARPU does not rescue
it because break-even ≈ uplift regardless, and that the guard is therefore set
at 2% in code before any cohort ships.

**④ Intellectual honesty as a differentiator.**
Published results on our primary dataset reach ~97% accuracy and ~0.99 AUC. We
reproduce them, then show they are wrong — inflated by duplicate rows and a
leaky field. We separate the label's behavioural *drivers*, which the model
legitimately sees, from its *artefacts*, which it must never see, and test both
directions. We state that our leakage detector's *distribution* is grounded in
real data while its *predictive power* is not yet validated. **We would rather
show a defensible 0.78 PR-AUC than an indefensible 0.99.**

### Anticipated questions

| | |
|---|---|
| *"Your population is generated — how do we know it works?"* | Three answers. The structure is learned adversarially and gated by a detection test. The prices are the operator's real catalogue. And the uplift method is validated on 25M rows of real randomised treatment and control before it touches generated data. What remains generated is the population, and we say so. |
| *"Does your leakage detector actually predict churn?"* | Not in the data we can test it on, and we say so. In 100,000 real subscribers it shows no separation — 0.282 against 0.278. Expected: that is a single-SIM postpaid market with no receiving-SIM behaviour to detect. The source grounds the *distribution*; the *predictive* claim is specific to dual-SIM prepaid and testable only on real Libyan data. |
| *"How can you train on a label you generated?"* | The hazard is a function of observable behaviour so the signal is recoverable — deliberate, because a model that sees no driver of its label has nothing to learn. What it never sees are the artefacts: hazard score, churn date, the label itself. Both directions are tested. And this demonstrates the pipeline works, not that the model would perform this way in production. |
| *"Why isn't everything deep learning?"* | We benchmarked it. On tabular telecom data gradient boosting matched or beat the LSTM at a fraction of the compute, and SHAP gives regulator-grade explanations. We report whichever arm won and explain why. |
| *"Why does the catalogue matter if you could invent offers?"* | Because two of the things this system does need it. "Is this offer worthwhile" requires knowing what revenue you would destroy, which only exists against a real catalogue. And "recommend the best action" requires an executable one — *"give them 4.2 LYD of value"* cannot be actioned or checked. An invented offer also has an invented cost, which would make the margin floor enforce one made-up number against another. |
| *"What breaks first at scale?"* | The feature store. DuckDB is correct at demo scale; at millions of subscribers it becomes a columnar warehouse with the same schema. Models and decision logic are unchanged. |

---

## Appendix A — Integration

Six frozen endpoints, consumed read-only by Components 4 and 5 over HTTP:
`/v1/cohort/query` · `/v1/score/churn` · `/v1/subscriber/{id}` ·
`/v1/offer/next-best` · `/v1/price/quote` · `/v1/advance/limit`.

They call rather than import, for four reasons: the feature store will be
replaced at scale, importers bypass the guardrails, importers skip the audit
log, and components need to deploy independently.

Identifiers are salted SHA-256 hashes; a raw MSISDN returns 422. Everything is
read-only — `/v1/offer/next-best` *computes* an offer, it does not send one.

**What we need from Component 2**, keyed by hashed subscriber ID:
`dropped_call_rate_30d`, `data_session_failure_rate`,
`service_outage_hours_30d`. Until it exists the synthesis engine generates the
same field names, so swapping the source changes nothing downstream.

**Grounding rules for LLM consumers:** never set a price or a limit; never
invent a number; cite the tool output; refuse rather than guess; never expose a
raw identifier; never cache a decision. Full contract and worked example:
`docs/INTEGRATION.md`.

## Appendix B — Definition of Done

A module is complete only when it has unit tests in CI, is reachable through
the API, is visible in the UI, is logged in MLflow with metrics, has a model
card or data-dictionary entry, has every commercial figure it depends on
recorded with a provenance status, and survives `docker compose up` from a
clean clone **on a machine that is not the author's**.

The last one is what catches people.
