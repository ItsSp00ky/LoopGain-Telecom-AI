# AI Customer Value Management (CVM)

### Component 3 of the Telecom AI Platform — Samsung Innovation Campus, Libya AI 2026

| Field | Detail |
|---|---|
| **Component** | Customer Intelligence, Retention & Loyalty |
| **Operator modelled** | Almadar Aljadid — المدار الجديد (MCC/MNC 606-01), under LPTIC |
| **Competitor modelled** | Libyana (606-00) — as the destination of share-of-wallet leakage only |
| **Repository** | `ali_branch` |
| **Duration** | 3 weeks (15 working days) |
| **Infrastructure** | CPU-only core; free-tier GPU for one module. Total budget ≤ $20 |
| **Integration** | Four HTTP endpoints consumed read-only by the Chatbot and Employee Copilot |

---

## 1. Executive Summary & Problem Statement

### 1.1 Executive Summary

Almadar Aljadid serves a Libyan mobile market that is overwhelmingly **prepaid**.
That single fact removes everything a conventional retention system is built on.
There is no contract, no billing relationship, and no cancellation event. A
customer does not leave. They stop topping up, and revenue disappears from the
base without a single event being logged.

The **AI CVM component** is a decision-intelligence layer over data the
operator already produces — recharge logs, bundle purchases, usage records,
service-quality indicators, emergency-credit history — that produces four
operator-grade outputs per subscriber:

1. A calibrated **silent-churn probability** and an estimated time-to-churn window.
2. A **value and loyalty tier** from a prepaid-adapted RFM model plus predicted
   lifetime value.
3. A **dynamically priced offer** drawn from Almadar's real catalogue,
   loyalty-weighted and margin-constrained, able to reach for the operator's own
   1 LYD unlimited morning pass — a product that costs the network almost
   nothing on idle capacity.
4. A **personalised emergency-credit limit** for both of Almadar's airtime and
   data advance products, replacing rules that gate on the subscriber being
   nearly out of money and then size the advance by "consumption".

All four are reachable through a documented API, a campaign console, and an
Arabic subscriber-channel simulator. The system runs end-to-end in Docker on a
student laptop in four containers under 3 GB of RAM. One module trains on a
free GPU session. Nothing in the design requires production hardware.

**The component is anchored to the operator's real commercial reality**, not to
a generic telecom template: 57 published bundles across 17 families, the
confirmed 3/5/10/20/40/100 LYD recharge ladder, published pay-as-you-go
tariffs, and both emergency-credit services documented from the operator's own
material.

### 1.2 The Business Pain Points

Five structural failures, each an addressable engineering problem.

**P1 — Silent churn is invisible until it is irreversible.**
In postpaid markets churn is a signed cancellation. Here it is an absence: no
top-up for 30, then 60, then 90 days, followed by number recycling. By the time
a monthly report shows ARPU decline, the subscriber's social graph has already
migrated to the competing SIM. There is no event to react to, only a decaying
signal nobody watches per-subscriber.

**P2 — Dual-SIM share-of-wallet leakage, at scale.**
Carrying both an Almadar and a Libyana SIM is not a niche behaviour; it is the
norm, driven by patchy coverage and on-net pricing. At that penetration
"active" is close to meaningless as a retention metric. A subscriber can stay
technically active while most of their spend has moved. Conventional churn
models score them as retained; in revenue terms they are half-lost.

The leading indicator is measurable and currently unmeasured: **incoming-call
volume holding steady while outgoing volume and off-net share both rise.** That
subscriber has quietly made this their *receiving* SIM.

Almadar's own tariff structure sharpens this. On-net voice is billed as a
three-minute block at 90 dirham, then 50 dirham per minute; off-net is a flat 90
dirham per minute. So the marginal on-net minute is genuinely cheaper, and a
subscriber drifting toward off-net calling is paying measurably more to do it.
That is an economically motivated signal, not a statistical artefact.

**P3 — A rich catalogue with no per-subscriber logic behind it.**
Almadar publishes 57 distinct bundles: five Mix tiers crossed with four
durations, unlimited Golden and speed-capped Silver tiers, daily packs from 0.5
LYD, hourly Macchiato passes, social bundles, 5G monthly tiers up to 600 GB, and
shared Family plans for three to five members.

That is more than enough product variety for genuine personalisation. What is
missing is the machinery to decide *which* of the 57 a given subscriber should
be offered, at what price, and when. The catalogue is broadcast; it is not
targeted. A nine-year customer and a SIM activated last week browse the same
USSD menu.

**P4 — Blanket promotions destroy margin, and the catalogue makes it worse.**
Mass discount campaigns are the default retention instrument and are
indiscriminate. A large share of the incentive lands on subscribers who would
have recharged anyway; another share lands on subscribers already gone. Net
margin impact is never isolated because there is no holdout group.

There is a second, sharper risk specific to this catalogue. The morning pass is
1 LYD for unlimited data *and* voice. The monthly Mix tiers run 20–75 LYD.
Handing a cheap unlimited pass to a heavy user who is not actually at risk does
not just waste the incentive — it invites them to **downgrade off a monthly
bundle they were happily paying for**. On this price sheet, cannibalisation is a
larger financial risk than the incentive spend itself, and §7.2 quantifies it.

**P5 — Emergency credit is allocated without a risk model, and its cheapest
failure mode is invisible.**

This is the sharpest finding in the project, and it comes from the operator's
own published documentation rather than from assumption.

Almadar operates **two** emergency-credit services:

| | **رصيد في وقته** (airtime) | **نت في وقته** (data) |
|---|---|---|
| Access | `*140#`, `*140*5#` | `*000#`, Almadar app |
| Amount | **1 / 3 / 5 LYD** | **flat 5 LYD** (2 GB, 3 days) |
| Eligibility | basic balance **≤ 0.5 LYD** | balance **≤ 1 LYD** *and* remaining quota **< 250 MB** |
| Allocation rule | *"according to the subscriber's consumption"* | none — identical for everyone |
| Settlement | recovered at first recharge; auto-settle check at 48 hours | recovered at first recharge or incoming transfer |
| Repeat | permitted same day once the debt is cleared | permitted once the debt is cleared |
| Interaction | mutually exclusive — data credit is blocked while the balance is negative | |

Four consequences follow directly.

**First, eligibility is the inverse of a risk filter.** Both products gate on
the subscriber being nearly out of money. The eligible population is therefore,
by construction, the population least able to repay. That is a reasonable design
for a *convenience* feature and an actively dangerous one for a credit product.

**Second, "according to the subscriber's consumption" is not a risk model.**
Consumption is not repayment probability. A heavy user in decline consumes a
great deal and repays badly; the rule cannot distinguish them from a heavy user
who is perfectly fine. The thresholds are not published, so the rule is opaque
as well as weak.

**Third, the data advance has no differentiation whatsoever.** Five dinars, two
gigabytes, three days, for every subscriber regardless of tenure, spend or
repayment history.

**Fourth — and this is the finding worth a slide — the debt can exceed what the
subscriber can pay in one transaction.**

```
    smallest recharge card sold ........ 3 LYD
    نت في وقته debt .................... 5 LYD
```

A subscriber whose habitual top-up is the smallest card **cannot clear a data
advance in a single recharge**. The debt persists. And because re-subscription
requires the debt cleared, they are locked out of the very service they reached
for — while an unpaid balance sits against the line.

The two services being mutually exclusive compounds it: a subscriber in
sustained difficulty **alternates between them**, taking airtime credit,
clearing it, taking data credit, clearing it. That alternation is a clean,
measurable distress signal, and nothing in the current design is watching for it.

The documentation also gives us something valuable: **a clean supervised
label**. Settled by the next recharge, yes or no. No synthetic guesswork is
required in the target definition.

### 1.3 Core Value Proposition

> **The CVM component converts passive prepaid telemetry into a per-subscriber,
> margin-constrained retention decision — daily, automatically, and with a
> defensible LYD figure attached to every action.**

This is deliberately **not a churn prediction project**. A churn score is an
input, not a product. The system closes the loop:

```
predict who is leaking → quantify what they are worth → decide what to offer
  → price it within margin, loyalty and credit guardrails → deliver it in Arabic
  → hold out a control group → measure realised uplift → retrain
```

Five design principles separate it from a classroom churn notebook.

| Principle | In practice |
|---|---|
| **Calibrated, not ranked** | Pricing consumes probabilities as monetary expectations, so a 0.31 must mean 31%. All classifiers are probability-calibrated and scored on Brier and PR-AUC, never accuracy. |
| **Uplift, not propensity** | Budget goes only to *persuadables*. Never to sure things, never to lost causes. |
| **Value-add before discount** | Loyalty is rewarded with the operator's 06:00–11:00 morning pass — near-zero marginal cost on idle capacity — in preference to headline price cuts that permanently erode ARPU and are trivially matched. |
| **Credit that protects, not traps** | The advance limit is capped by repayment probability, lifetime value, **and what one typical top-up can actually clear**. A 5 LYD debt against a 3 LYD card is a trap, not a service. |
| **Localised by construction** | Target definition, feature set, price sheet, tariff structure and offer copy encode Almadar's actual commercial reality rather than adapting a US postpaid dataset. |

### 1.4 Module Scope

Four modules. Each answers one question, and each feeds the next.

| # | Module | Question it answers | Code |
|---|---|---|---|
| **M1** | **Silent Churn Engine** — LightGBM vs LSTM benchmark | Who stops generating revenue in 30 days, and *when*? | `src/cvm/models/m1_churn/` |
| **M2** | **Value & Loyalty Tiering** — RFM-LE, clustering, PCA, CLV | What is this subscriber worth, and how loyal? | `src/cvm/models/m2_value/` |
| **M3** | **Dynamic Pricing & Off-Peak Offloading** | Which of 57 bundles, at what price, for *this* subscriber, within margin? | `src/cvm/decision/` |
| **M4** | **Smart Advance** — learned emergency-credit limit | How much credit can we safely extend, and to whom? | `src/cvm/models/m4_advance/` |

**Scope boundaries, stated deliberately.** This component does not model:

- **The network.** Congestion forecasting and cell anomaly detection belong to
  Component 2. CVM consumes per-subscriber service-quality signals as ordinary
  churn features and does not reproduce the analysis behind them.
- **Geography.** No districts, no cell identifiers, no coordinates. All
  subscribers are modelled as geographically equivalent. Service quality varies
  per subscriber, not per place.
- **Complaint text.** Care-contact *volume* is a churn feature; care-contact
  *content* is the Customer Chatbot's domain.
- **Conversational interfaces.** The Employee Copilot and Customer Chatbot are
  separate components. This one publishes the API they consume, and contains no
  agent and no LLM call path in any decision. That is a design constraint, not
  an omission — see §1.5.

Each boundary removes duplicated work and a dependency, and each is a seam the
owning component can fill later without this component changing.

### 1.5 Where This Sits in the Platform

The platform has five components. This is one of them.

| # | Component | Relationship to CVM |
|---|---|---|
| 1 | GIS & Network Planning | Independent |
| 2 | Network ML — congestion, anomaly detection | **Supplies** per-subscriber service-quality signals we consume as churn features |
| **3** | **Customer Intelligence, Retention & Loyalty** | — |
| 4 | Customer Chatbot | **Consumes** the offer and eligibility endpoints |
| 5 | Employee Telecom Copilot | **Consumes** the cohort and scoring endpoints |

Components 4 and 5 reach CVM over **HTTP, read-only**. They do not import the
package and they do not query the feature store. Four reasons that seam is
drawn there rather than at the library level:

1. **The feature store will be replaced at scale.** DuckDB is correct at demo
   scale; at millions of subscribers it becomes a columnar warehouse. A
   consumer that queries the file breaks on that day. A consumer that calls the
   API does not.
2. **Guardrails must not be bypassable.** Every price and every credit limit
   passes six constraints before it leaves the decision engine. An importer can
   call the pricing function directly and skip them. An HTTP caller cannot.
3. **The audit log.** Every decision persists its inputs, weights, active
   constraints and reason codes. Decisions taken through the API are logged;
   decisions taken by importing a function are not, and "why did this subscriber
   get this offer?" becomes unanswerable.
4. **Independent deployment.** Components ship on different days without
   coordinating a merge.

The published contract, with a worked example, is Appendix B.

---

## 2. Datasets & Data Pipeline

### 2.1 Strategy: Real Structure, Real Prices, Generated Population

No public Libyan CDR dataset exists, and none should — subscriber data cannot
legally or ethically leave an operator. The corpus is built in three layers:

- **Real public datasets** supply the statistical structure of telecom
  behaviour: usage distributions, churn base rates, feature correlations,
  service-quality indicators, and genuine labels for validation.
- **The operator's real catalogue and tariffs** fix the monetary scale. Prices,
  bundle volumes, recharge denominations and pay-as-you-go rates are not
  invented; they are transcribed from Almadar's published material into
  `conf/catalogue.yaml` and `conf/market.yaml`.
- **A conditional tabular GAN** generates the subscriber population itself,
  conditioned on the real features so joint structure is preserved.

The report and the pitch state this plainly. **Generated-population metrics are
not evidence of production performance.** The deliverable is a validated
pipeline and decision logic with a deployment-ready schema, priced against a
real catalogue.

Every value in the market configuration carries a `status` of `confirmed`,
`assumption` or `placeholder`, and `docs/MARKET_QUESTIONS.md` tracks which is
which. A number without recorded provenance is treated as a defect.

### 2.2 Primary Datasets

#### Dataset A — Iranian Churn Dataset (UCI ML Repository, ID 563) — PRIMARY

| Attribute | Value |
|---|---|
| Source | `archive.ics.uci.edu/dataset/563/iranian+churn+dataset` |
| Access | `from ucimlrepo import fetch_ucirepo; d = fetch_ucirepo(id=563)` |
| Size | 3,150 rows × 13 features + churn label |
| Licence | CC BY 4.0 |

Collected from an Iranian operator over 12 months. Features include call
failures, complaints, subscription length, charge amount, seconds of use,
frequency of use, frequency of SMS, distinct called numbers, age group, tariff
plan, status, a pre-computed *Customer Value* field, and the churn label.
Attributes aggregate months 1–9; the label is customer state at month 12, with a
3-month planning gap.

**Why it anchors the project:** it is the closest public analogue on four axes
at once. It is **prepaid**, it is **MENA-region**, it contains a **service-quality
feature** (`Call Failures`) that most churn datasets omit, and its **9-month
observation / 3-month prediction gap** is exactly the operational framing a real
campaign needs.

Two mandatory corrections before use:

1. Roughly **300 duplicate rows (~9.5%)** require exact-match deduplication.
2. The pre-computed **`Customer Value`** field partially encodes the outcome and
   is excluded from the feature matrix.

Both corrections are why our reported metrics sit below the published figures,
and §8.1 treats that gap as a result rather than an embarrassment.

#### Dataset B — Cell2Cell (Duke University / Teradata CRM Center) — SCALE & SEQUENCES

| Attribute | Value |
|---|---|
| Source | `kaggle.com/datasets/jpacse/datasets-for-churn-telecom` |
| Size | 71,047 instances × 58 features (51,048 labelled / 19,999 unlabelled holdout) |
| Class balance | ~29% churn in the labelled split |

Supplies volume and, critically, **trend and degradation features**: percent
change in minutes of use (`changem`), percent change in revenue (`changer`),
mean dropped voice calls (`dropvce`), blocked calls (`blckvce`), unanswered
calls (`unansvce`), care-call counts, handset attributes.

**Role:** this is where decay modelling is learned. The `changem` / `changer`
delta features are the direct ancestors of our `revenue_decay_ratio_7d_30d`, and
`dropvce` / `blckvce` seed the service-quality features. It is also large enough
to make the **LSTM benchmark in M1 meaningful** — an LSTM on 3,000 rows would
prove nothing. The unlabelled holdout serves as an inference load test.

#### Dataset C — IBM Telco Customer Churn (extended) — BENCHMARK & CLV

| Attribute | Value |
|---|---|
| Source | IBM Cognos community sample; mirrored on Kaggle |
| Size | 7,043 customers × ~19–33 features |
| Churn rate | ~27% |

The extended release includes **CLTV** (a benchmark lifetime-value target),
**Churn Reason** and **Churn Score**.

**Role:** an independent CLTV benchmark for M2; a sanity check that our modelled
churn drivers resemble real ones; and a small, fast dataset so the first
baseline is never blocked on pipeline work.

#### Dataset F — Criteo Uplift Prediction — UPLIFT VALIDATION

| Attribute | Value |
|---|---|
| Source | `ailab.criteo.com/criteo-uplift-prediction-dataset` |
| Mirror | `huggingface.co/datasets/criteo/criteo-uplift` |
| Size | 25M rows × 11 features + `treatment`, `conversion`, `visit`, `exposure` |
| Licence | free for academic and research use |

**This dataset does more for the project's credibility than any other.** The
uplift model in M3 decides who receives budget, and a generated population can
only validate it against response data we wrote ourselves. Criteo is a *real*
incrementality test with genuine randomised treatment and control arms.

**Role:** the uplift *method* is trained and validated here, then applied to the
generated population. That converts "our uplift model scores well on data we
made up" into "our uplift method is validated on 25M real randomised rows, then
applied to a Libyan population" — a direct answer to the sharpest question an
evaluator can ask.

The data is deliberately sub-sampled so the original incrementality level cannot
be recovered. It validates method, never an effect size.

#### Dataset G — Hillstrom MineThatData E-Mail Challenge — UPLIFT WARM-UP

64,000 customers across three randomised arms. Small enough to iterate on in an
afternoon, and the clearest available demonstration of the four uplift
quadrants — persuadable, sure thing, lost cause, and **sleeping dog**. The
sleeping-dogs guard is a stated commitment in §3.3, so having a dataset where it
is visibly necessary matters.

#### Dataset H — KKBox WSDM Churn Challenge — REAL DAILY SEQUENCES

~1M members with `transactions`, `members`, and genuinely **daily** `user_logs`.
Churn is defined as *no renewal within 30 days of expiry* — an absence, not a
cancellation, which is precisely our target definition. The closest public
analogue to prepaid silent churn, and the strongest real sequence signal
available to the M1 LSTM arm. Large; subsampled on ingestion.

#### Dataset J — UCI Online Retail II — CLV VALIDATION

1,067,371 transactions, CC BY 4.0, `fetch_ucirepo(id=502)`. The canonical
validation set for BG/NBD and Gamma-Gamma. M2's CLV implementation is proven
correct here, on real non-contractual transaction data with a genuine holdout,
before being pointed at recharges.

### 2.3 Market Facts: The Real Commercial Layer

This is what separates the project from a template. Every figure below is
transcribed from the operator's published material into version-controlled
configuration that the pricing engine reads at runtime.

#### Recharge ladder

**3, 5, 10, 20, 40, 100 LYD.**

Two consequences run through the whole design:

- The **3 LYD floor** is load-bearing for M4. It is what makes a 5 LYD data
  advance unclearable in one transaction.
- The cheapest bundle is **0.5 LYD**, so monetary fields are never rounded to
  whole dinars anywhere in the pipeline.

#### Pay-as-you-go tariffs

Quoted by the operator in dirham; 1000 dirham = 1 LYD.

| | LYD |
|---|---|
| Almadar → Almadar voice | **0.090 for the first 3 minutes**, then 0.050/min |
| Almadar → Libyana voice | 0.090/min |
| Almadar → landline | 0.040/min |
| SMS, on-net **and** off-net | 0.050 |
| SMS international | 0.250 |
| Data — *Bjawak* service | 0.025/MB |

Three structural facts the pipeline must respect:

**On-net voice is a block tariff, not a rate.** A one-minute call costs 0.090
LYD — effectively 0.090 per minute. A ten-minute call costs 0.440 LYD, or 0.044
per minute. Short calls are expensive and long calls are cheap, so generated
call *lengths* drive revenue per minute. Flattening this to a single average
rate would misprice most of the base.

**There is no on-net SMS discount.** Both directions cost 0.050. SMS therefore
carries no competitive pricing signal, and any leakage feature built on SMS
on/off-net mix would be noise dressed as insight. The feature configuration
excludes it by name, with the reason recorded. Voice does carry the signal.

**Pay-as-you-go data costs roughly 25× the bundle rate.** 0.025 LYD/MB is about
25 LYD per gigabyte; the 80 GB monthly bundle is 80 LYD, or 1 LYD per gigabyte.
That makes `bundle_vs_payg_share` far stronger than a ratio in a normal market.
A subscriber paying PAYG data rates is either **unaware** of the catalogue or
**unable to afford** a bundle's up-front cost. Those are different problems
requiring different interventions — one is a communications problem, the other
an affordability problem — and M3 must not send the same offer to both.

#### Bundle catalogue — 57 bundles across 17 families

| Family | Range | Notes |
|---|---|---|
| **عروض الصبح** Morning | 1 LYD | **Unlimited data AND voice, 06:00–11:00.** The off-peak anchor |
| **مكس** Mix — Diamond / Platinum / Gold / Silver / Bronze | 1–75 LYD | Five tiers × four durations; data + voice; 8/16 Mbps |
| **الباقات الذهبية** Golden | 10–160 LYD | Unlimited data, 1 / 3 / 7 / 30 days |
| **الباقات الفضية** Silver | 8–130 LYD | Unlimited at 8 Mbps |
| **عروض يومية** Daily | 0.5–3 LYD | 50 MB up to 512 MB. The affordability floor |
| **عروض اسبوعية** Weekly | 5–8 LYD | 1–2 GB |
| **عروض شهرية** Monthly | 20–80 LYD | 6–80 GB |
| **الباقات الشهرية 5G** | 120–400 LYD | 100–600 GB |
| **باقات الساعة 5G** Hourly | 5–10 LYD | Unlimited within 1 or 2 hours |
| **ميكياتو** Macchiato | 2–3 LYD | Unlimited within 1 or 2 hours |
| **عروض Social** | 1–20 LYD | App-restricted |
| **عروض إيليت** Elite | 100–200 LYD | 120–300 GB, 30–60 days |
| **باقات حصتي معاك** Family | 90–250 LYD | Shared across 3–5 members |

No apps are zero-rated: all traffic consumes allowance.

**The morning pass is the most commercially interesting line in the catalogue.**
One dinar for unlimited data *and* unlimited voice, valid only 06:00–11:00. It
tells us two things at once: that the operator has already identified and priced
its own spare capacity, and precisely **when** that capacity is. The off-peak
trough is the morning, not the night.

That makes M3's off-peak strategy the **personalisation of a product that
already exists**, rather than the proposal of one that does not — a materially
stronger position under questioning. It also means the cannibalisation risk is
real rather than theoretical: 06:00–11:00 covers the commute and the working
morning, which is genuine usage time for a large part of the base.

Bundle volumes for several families are derived from their published names
(`نت 6` → 6 GB). The `variable_cost_lyd` on every bundle is an **estimate** —
25% of price for metered data, 35% for unlimited — because the operator's
marginal cost of a gigabyte is not public and the margin-floor guardrail
requires a figure to enforce. The obligation is to label the estimate, and the
report does.

#### Emergency credit products

Both services as documented in §1.2, transcribed field-by-field into
`conf/catalogue.yaml`. Notably, neither publishes a grace period and neither
documents a line-degradation or number-recycling outcome, so the M4 label
horizon is **behavioural** — settled by the next recharge, censored at 14 days —
rather than contractual, and the harm M4 prevents is **service lockout** rather
than line loss.

#### Base and economics

| | Value | Status |
|---|---|---|
| Addressable prepaid subscribers | 1,000,000 | estimate |
| Monthly ARPU | 30 LYD | estimate |
| Monthly silent churn | 3.5% | estimate |
| Dual-SIM penetration | 85% | estimate |

These four are clearly labelled estimates rather than operator figures, and the
business case in §7 is explicitly a method demonstration rather than a forecast.

Two of them shape the modelling rather than just the arithmetic. **ARPU at 30
LYD** is consistent with a catalogue whose cheapest monthly bundle is 20 LYD —
the figure has to clear the price sheet or it implies almost nobody buys one.
**Dual-SIM at 85%** means dual-SIM is the norm rather than a segment, which
promotes `incoming_outgoing_ratio` from a clever additional feature to the
central one: if most of the base holds two SIMs, "active" tells you very little
and share-of-wallet tells you most of what matters.

#### Calendar

| | Value | Status |
|---|---|---|
| Off-peak trough | 06:00–11:00 | **confirmed** by the morning pass |
| Evening peak | 19:00–22:00 | estimate |
| Public-sector salary window | days 25–30 | estimate |
| Weekend | Friday–Saturday | confirmed |

The weekend enters the pipeline as a **flag and nothing more** — a derived
`is_weekend` boolean with no usage multiplier attached, because the multiplier
would be the guessed part. It is kept because the generated daily series must
carry a weekly rhythm: a series with no weekly structure is unrealistically
smooth, and feeding that to the M1 LSTM arm would handicap it through a
data-generation choice rather than on merit. It also lets M3 distinguish a
commuter from someone who sleeps in, which is exactly who the morning pass
suits.

### 2.4 Synthesis Engine

The public datasets have no concept of a scratch card, a zero-balance night, an
emergency data advance, or Almadar's price sheet. Those are generated
conditionally on the real features so joint structure is preserved.

A generator proposes synthetic subscriber rows, a discriminator tries to
separate them from real ones, and the two train adversarially until the
generator wins. The result is a non-existent population of Libyan subscribers
whose joint structure matches the real corpus it learned from.

**Pipeline:**

1. **Adversarial fit** — CTGAN (primary) and TVAE (challenger) on the real
   corpus, with a Gaussian copula as the classical baseline. Comparing all three
   is itself a reportable experiment.
2. **Quantile mapping** — real monetary fields mapped onto the Libyan scale. The
   Iranian `Charge Amount` field maps by quantile onto the confirmed recharge
   ladder, so a 90th-percentile spender lands on 40–100 LYD cards, not 3 LYD.
3. **Business-rule overlays** — constructs the real data cannot supply:
   subscriber-level service-outage exposure, public-sector salary-week recharge
   spikes, the Friday–Saturday rhythm, emergency-credit behaviour for both
   products, and the 06:00–11:00 usage bump for subscribers who buy the morning
   pass.
4. **Explicit hazard function** for label generation, documented in the
   repository, so the model has recoverable signal and the evaluation is honest
   about being a simulation ground truth.
5. **Quality gate** (`SDMetrics`): KS-complement ≥ 0.85 on continuous
   marginals, pairwise correlation delta ≤ 0.10, and a **discriminator detection
   test** — a LightGBM classifier trained to separate real from synthetic should
   reach AUC ≤ 0.65. Above that, the generator is rejected and retrained.

That final gate is worth emphasising in the pitch: **the GAN is evaluated with
an adversarial test, the same principle that trains it.** It is also the primary
mitigation against the single biggest risk in the register — generated data that
is too clean, making models look unrealistically good.

Three overlays are worth calling out because they are anchored to confirmed
facts rather than guessed:

- The **06:00–11:00 usage bump** exists because the morning pass exists and is
  time-boxed to exactly those hours.
- **Emergency-credit behaviour** must reproduce three specific things or M4 has
  nothing to find: eligibility triggering at low balance rather than at tenure;
  a proportion of subscribers left holding debt larger than their habitual
  top-up; and distressed subscribers alternating between the two mutually
  exclusive products.
- The **weekly rhythm**, for the reason given in §2.3.

### 2.5 Generated Field Specification

**Monetary and recharge dynamics**

| Field | Generation logic |
|---|---|
| `recharge_amount_lyd` | Multinomial over the confirmed ladder {3, 5, 10, 20, 40, 100} LYD, weighted to low denominations, conditioned on value percentile |
| `modal_recharge_amount_lyd` | The subscriber's most common top-up. **Basis of the M4 affordability ceiling** — the mean is inflated by one salary-week top-up they will not repeat |
| `recharge_channel` | {scratch_card, agent_erecharge, almadar_app, bank_card, p2p_transfer}, weighted to scratch/agent given low banking penetration |
| `recharge_count_30d` / `_90d` | Poisson, λ from mapped spend percentile |
| `days_since_last_topup` | Inter-arrival sampling. **The strongest single churn signal in prepaid** |
| `mean_inter_recharge_days` | Mean gap over 90d |
| `recharge_gap_cv` | Coefficient of variation of gaps — irregularity precedes exit |
| `balance_zero_hours_30d` | Hours at zero balance. No postpaid equivalent exists |
| `failed_bundle_attempts_30d` | Purchases rejected for insufficient balance — pure affordability signal |
| `credit_transfer_out_lyd` | Peer-to-peer credit sharing |

**Emergency-credit dynamics (M4)**

| Field | Notes |
|---|---|
| `airtime_advance_count_90d` | Uses of رصيد في وقته |
| `airtime_advance_amount_lyd` | Constrained to the real denominations {1, 3, 5} |
| `data_advance_count_90d` | Uses of نت في وقته. Always 5 LYD; there is no tiering |
| `advance_settled_by_next_recharge` | **Supervised label for M4.** Behavioural, not contractual |
| `days_to_settle` | Settlement lag, censored at 14 |
| `unpaid_advance_days` | Days carrying unpaid debt. Debt blocks re-subscription, so this measures lockout |
| `emergency_service_alternations_90d` | Switches between the two products. **Sustained distress the incumbent design cannot see** |
| `advance_exceeded_modal_recharge_flag` | The 3-LYD-card / 5-LYD-debt trap, made measurable per subscriber |
| `balance_at_advance_lyd` | Always ≤ 0.5 (airtime) or ≤ 1.0 (data) — the gate, and why the population is selected on being broke |

**Usage, mix and leakage dynamics**

| Field | Why it matters |
|---|---|
| `data_mb_peak` / `data_mb_offpeak` | Off-peak is the 06:00–11:00 window |
| `offpeak_data_ratio` | Identifies who would actually use a morning pass |
| `voice_min_onnet` | Billed as a 3-minute block then per minute, so call length drives revenue |
| `voice_min_offnet` / `voice_min_landline` | Flat per-minute; landline is the cheapest destination |
| `onnet_ratio` | **Dual-SIM leakage proxy** — falling on-net share means the social graph is migrating |
| `incoming_outgoing_ratio` | **Primary leakage detector** — rising incoming against flat outgoing means "this is my receiving SIM" |
| `distinct_called_numbers_trend` | Contraction of the calling graph precedes silent exit |
| `payg_data_mb_30d` / `payg_data_spend_lyd_30d` | Data bought at ~25× the bundle rate |
| `bundle_vs_payg_share` | Unaware of the catalogue, or unable to afford it. Two different interventions |
| `social_bundle_share` | Share of spend on the real Social family |
| `ussd_price_check_sessions_30d` | Repeated catalogue browsing indicates active price shopping |

**Service quality (subscriber-level)**

Real measured features, not invented ones: seeded from the UCI `Call Failures`
column and Cell2Cell's `dropvce` / `blckvce` / `unansvce`.

| Field | Notes |
|---|---|
| `dropped_call_rate_30d` | Seeded from real data, perturbed per subscriber |
| `data_session_failure_rate` | Correlated with dropped-call rate |
| `service_outage_hours_30d` | Power- and fuel-driven downtime this subscriber experienced |

**Care contact, tenure and context**

| Field | Notes |
|---|---|
| `care_contacts_30d` / `care_contacts_trend` | Volume, not content. A rising trend precedes exit |
| `tenure_months`, `consecutive_active_months` | Loyalty backbone |
| `salary_week_flag` | Public-sector disbursement drives a pronounced recharge spike |
| `is_weekend` | Friday–Saturday. Flag only, no multiplier |
| `diaspora_roaming_flag` | Roaming marks a high-value, low-churn segment |
| `language_pref` | Drives message rendering. **Never a pricing input** |
| `subscriber_id_hashed` | SHA-256 + salt. **No raw MSISDN exists anywhere in the repository** |

### 2.6 Feature Engineering & Prepaid-Adapted RFM

#### Redefining RFM for prepaid

Textbook RFM assumes purchase transactions. Prepaid has none, so each dimension
is redefined and two are added.

| Dim | Standard | **Our prepaid definition** |
|---|---|---|
| **R — Recency** | Days since last purchase | Days since last **revenue-generating event** (top-up or bundle purchase). Usage alone does not count: a subscriber burning residual credit generates no revenue. |
| **F — Frequency** | Transaction count | Recharge count in 90d, **penalised by `recharge_gap_cv`**. Five regular recharges beat five erratic ones. |
| **M — Monetary** | Total spend | Total LYD in 90d, **plus the 30d-vs-prior-60d slope**, so decline is visible inside the score itself. |
| **L — Loyalty** | *(added)* | `0.4·tenure_scaled + 0.3·consecutive_active_months_scaled + 0.3·lifetime_recharge_percentile` |
| **E — Engagement** | *(added)* | Service breadth: distinct service types used (voice, SMS, data, bundles, transfers, advances), normalised. |

Quintile scoring 1–5 per dimension produces an `R|F|M|L|E` cell, collapsed into
eight business segments: Champions, Loyal High-Value, Potential Loyalists,
Promising New, Needs Attention, At-Risk Valuable, Hibernating, Lost.

#### Derived feature families

| Family | Representative features |
|---|---|
| **Velocity / decay** | `revenue_decay_ratio = mean_7d / mean_30d`, plus equivalents for data, voice, SMS. Values well below 1.0 are the earliest reliable tell |
| **Volatility** | Std-dev and CV of inter-recharge gaps; rolling variance of daily data usage |
| **Calendar** | `is_weekend`, `weekend_usage_share_30d`, `is_salary_week`. Derived, never imposed |
| **Ratios & mix** | `onnet_ratio`, `offpeak_data_ratio`, `bundle_vs_payg_share`, `payg_data_spend_lyd_30d`, `data_to_voice_ratio` |
| **Distress** | `balance_zero_hours`, `failed_bundle_attempts`, downgrades, consecutive smallest-card recharges |
| **Leakage** | `incoming_outgoing_ratio` trend, off-net share trend, distinct-called-numbers contraction. SMS mix excluded by design — no on-net discount means no signal |
| **Credit** | Advance frequency per product, settlement lag, unpaid days, service alternation, modal recharge |
| **Service quality** | Dropped-call rate, session failure rate, outage hours — subscriber-level |
| **Sequence tensors** | Per-subscriber 90 × *k* daily matrices of recharge, data, voice, SMS. **Direct input to the M1 LSTM — no aggregation applied** |

### 2.7 Leakage Controls

Three invariants, each enforced by an automated test that is a required CI gate.

**1. Point-in-time correctness.** All features are computed over an observation
window ending strictly before the label window opens: 90-day observation, 15-day
gap, 30-day outcome.

**2. Temporal splits, never random.** A random split leaks the future. There is
deliberately no `random_split` function anywhere in the codebase, and a test
asserts its continued absence.

**3. Label artefacts excluded; label drivers retained.** This distinction is
subtle and getting it wrong breaks the project in opposite directions, so it is
made explicit in code rather than left to discipline.

- **Label artefacts** — `hazard_score`, `churn_date`, the label itself,
  `days_to_churn` — must never reach the feature matrix. Any one of them lets a
  model reconstruct the outcome directly, producing a model that scores
  beautifully and knows nothing. This is the single most damaging failure
  available to the project.
- **Label drivers** — `days_since_last_topup`, `recharge_gap_cv`,
  `balance_zero_hours_30d`, `onnet_ratio`, `incoming_outgoing_ratio`,
  `service_outage_hours_30d` — are the behavioural fields the hazard is a
  function of, and they **remain available as features**. The hazard is built
  from observable behaviour precisely so the signal is recoverable. A model that
  can see no driver of its own label has nothing to learn, and every metric
  collapses for a reason that is extremely difficult to trace.

The test suite asserts **both** directions and that the two sets are disjoint,
so a future well-intentioned tightening of leakage control cannot silently gut
the feature set.

What makes the driver overlap honest rather than circular is stated plainly in
the report: these metrics are computed against a simulation whose ground truth
we wrote. They demonstrate that the pipeline and the decision logic work. They
are not evidence of production performance, and the real-data validation path is
specified in §6.4.

The same discipline applies to the UCI `Customer Value` field, which partially
encodes the outcome and is dropped — and that is why our reported metrics sit
below the published ones.

---

## 3. System Architecture & Methodology

### 3.1 Data Flow

```
┌──────────────────────────────────────────────────────────────────────────┐
│  LAYER 0 — SOURCES                                                       │
│  [UCI Iranian 3,150]   [Cell2Cell 71,047]   [IBM Telco 7,043]            │
│  [Criteo Uplift 25M]   [Hillstrom 64k]      [KKBox]   [Online Retail II] │
│  + Almadar catalogue, tariffs and recharge ladder (conf/)                 │
└──────────────────────────────┬───────────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  LAYER 1 — INGESTION & LANDING                       (Python · PyArrow)  │
│  Pandera schema contracts · dedup (~300 UCI dups) · MSISDN → SHA-256     │
│  raw → Parquet, partitioned by snapshot_date                             │
└──────────────────────────────┬───────────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  LAYER 2 — GAN SYNTHESIS ENGINE                                          │
│                                                                          │
│   ┌───────────┐        generated rows        ┌───────────────┐           │
│   │ Generator │ ───────────────────────────► │ Discriminator │           │
│   └─────▲─────┘                              └───────┬───────┘           │
│         │            adversarial loss                │                   │
│         └────────────────────────────────────────────┘                   │
│              CTGAN (primary) · TVAE · Copula (baseline)                  │
│                               │                                          │
│      quantile → LYD ladder  →  overlays: outage · salary week ·          │
│                                weekend · emergency credit · 06:00-11:00   │
│                               │                                          │
│   [ QUALITY GATE: KS ≥ 0.85 · corr Δ ≤ 0.10 · detection AUC ≤ 0.65 ]     │
│                               │  reject → retrain                        │
└──────────────────────────────┬───────────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  LAYER 3 — TRANSFORM & FEATURE STORE            (DuckDB · Polars)        │
│  rolling 7/30/90d aggregates · RFM-LE quintiles · decay & leakage ratios │
│  weekly rhythm · subscriber-level service quality                        │
│  ────────────────────────────────────────────────────────────────────    │
│  features_offline.parquet  (point-in-time correct, for training)         │
│  sequences_offline.npz     (90 × k daily tensors, for the LSTM)          │
│  features_online.duckdb    (serving, read-only)                          │
└──────────────────────────────┬───────────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  LAYER 4 — MODEL LAYER                                                   │
│                                                                          │
│  M1 CHURN — head-to-head benchmark                                       │
│    ┌────────────────────────┐   ┌────────────────────────┐               │
│    │ Arm A: LightGBM on     │vs │ Arm B: LSTM on raw     │               │
│    │ engineered features    │   │ daily sequences (Keras)│               │
│    └────────────────────────┘   └────────────────────────┘               │
│    + Cox PH survival → time-to-churn window                              │
│                                                                          │
│  M2 VALUE — RFM-LE rules ∥ K-Means ∥ Hierarchical ∥ PCA                  │
│           + BG/NBD & Gamma-Gamma CLV                                     │
│                                                                          │
│  M4 ADVANCE — two repayment PD heads, sharing M1's feature pipeline      │
│                                                                          │
│                     ▼                                                    │
│            [ MLflow Tracking ] ──► artifacts/models/                     │
└──────────────────────────────┬───────────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  LAYER 5 — DECISION ENGINE  ★ the commercial core ★                      │
│                                                                          │
│  churn_prob ─┐                                                           │
│  time-to-churn│  ┌──────────────┐   ┌──────────────────┐                 │
│  CLV ─────────┤  │ Uplift filter│──►│ M3 Pricing:      │                 │
│  loyalty_idx ─┼─►│ persuadables │   │ 57-bundle choice │                 │
│  repay_PD ────┤  │ only         │   │ + morning pass   │                 │
│  net_quality ─┘  └──────────────┘   └────────┬─────────┘                 │
│                                              ▼                           │
│           ┌──────────────────────────────────────────────┐               │
│           │ GUARDRAILS: margin floor · CLV ceiling ·      │               │
│           │ budget LP · cannibalisation · fairness ·      │               │
│           │ full decision log                            │               │
│           └────────────────────┬─────────────────────────┘               │
│                                ▼                                         │
│   { offer_id, price_lyd, bonus, valid_hours, advance_limit_lyd,          │
│     stage, reason_codes[], expected_margin_lyd, decision_log_id }        │
└──────────────────────────────┬───────────────────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  LAYER 6 — SERVING API                       (FastAPI · Pydantic v2)     │
│  /v1/cohort/query   /v1/score/churn      /v1/offer/next-best            │
│  /v1/price/quote    /v1/advance/limit    /v1/subscriber/{id}   /health   │
│  target p95 < 200 ms, single CPU container                               │
└────────┬──────────────────────┬───────────────────────┬──────────────────┘
         ▼                      ▼                       ▼
┌──────────────────┐  ┌───────────────────┐  ┌──────────────────────────┐
│ 7a CVM COMMAND   │  │ 7b CHANNEL SIM    │  │  OUTSIDE THIS COMPONENT  │
│ CENTER           │  │ USSD + SMS        │  │  Component 4 Chatbot     │
│ exec KPIs ·      │  │ Arabic RTL        │  │  Component 5 Copilot     │
│ segments ·       │  │ *140# / *000#     │  │  → read-only HTTP        │
│ subscriber 360 · │  │ menu mock         │  │  → see Appendix B        │
│ campaign builder │  │ LLM-written copy  │  │                          │
└──────────────────┘  └───────────────────┘  └──────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  LAYER 8 — MLOps   Docker Compose · GitHub Actions · pytest · MLflow     │
│  Evidently drift · model cards · decision audit log · leakage test       │
└──────────────────────────────────────────────────────────────────────────┘
```

**Runtime footprint:** four containers (`api`, `ui`, `channel-sim`, `mlflow`),
CPU-only at serving time, under 3 GB RAM. The LSTM arm trains separately on a
free GPU session and ships as a saved artefact.

There is no agent container, which is the strongest available enforcement of
"no LLM in a path that moves money" — the path does not exist.

### 3.2 Models and Their Roles

#### M1 — Silent Churn Engine: a genuine architecture benchmark

This module is deliberately structured as an experiment rather than a single
model, because the experiment is more informative than either arm alone.

**Arm A — LightGBM on engineered features**

| | |
|---|---|
| Algorithm | LightGBM primary; XGBoost and CatBoost challengers; Decision Tree and Logistic Regression as interpretable baselines; Naïve Bayes, KNN and SVM reported alongside |
| Input | ~80 engineered features from §2.6 |
| Tuning | Optuna, time-boxed to 50 trials |

The classical baselines are **reported, not discarded**. A boosted model that
only narrowly beats logistic regression is a useful thing to know before
shipping the complex one.

**Arm B — LSTM on raw daily sequences**

| | |
|---|---|
| Architecture | Input `(90, k)` daily tensor → Masking → LSTM(64) → Dropout(0.3) → LSTM(32) → Dense(16, ReLU) → Dense(1, sigmoid) |
| Framework | TensorFlow / Keras |
| Regularisation | Dropout and early stopping |
| Input | Raw daily recharge, data, voice, SMS. **No hand aggregation** — the point is whether the network learns the decay patterns engineered by hand in Arm A |

Two things the write-up states in words rather than leaving implied: overfitting
is controlled by dropout and early stopping rather than by hope, and gating is
why this is an LSTM and not a plain recurrent network — it is the mechanism that
lets gradient survive 90 timesteps.

**Shared framing for both arms:** 90-day observation → 15-day gap → 30-day
outcome. Target is zero revenue-generating events for ≥ 30 consecutive days in
the prediction window. Temporal split, never random. Class weighting first, with
SMOTE/ADASYN as a documented comparison applied **inside** CV folds. Both arms
are probability-calibrated with isotonic regression, because the pricing engine
consumes probabilities as monetary expectations.

**Metrics:** PR-AUC (primary), lift @ decile 1–3, Brier score, ROC-AUC
(secondary). **Accuracy is not reported** — it is meaningless at a 10–30% base
rate, and CI fails if it appears as a headline.

**Why this benchmark is worth a slide.** Either outcome is a result. If the LSTM
wins, sequential structure carries information the engineered features discard,
and we say so. If LightGBM wins — the likelier outcome on short, sparse prepaid
histories — we explain *why*: 90 timesteps of mostly-zero daily activity is a
weak sequence signal, gradient boosting is extremely strong on tabular data, and
the engineered decay ratios already encode most of the temporal information.
Demonstrating an informed architecture choice is a stronger technical signal
than defaulting to a neural network because it sounds advanced.

**Explainability:** SHAP TreeExplainer on Arm A, with per-subscriber waterfall
plots surfaced in the UI **in plain language** — "has not topped up in 23 days",
not a feature name and a coefficient. SHAP contributions are aggregated to
feature-family level, because eighty individual contributions are not legible to
a marketing analyst. Arm B is compared on calibration and lift rather than
interpretability, and the gap is discussed rather than papered over.

**M1b — Time-to-Churn.** `lifelines` Cox Proportional Hazards, with a Random
Survival Forest challenger. Classification answers *if*; survival answers
*when*. Retention economics are timing-sensitive: intervening 40 days early
wastes budget, 5 days late wastes everything. The Cox output sets campaign
trigger windows and **defines the stage boundaries of the retention ladder in
§3.3**. Concordance index is the reported metric.

#### M2 — Value Segmentation & CLV

Three unsupervised techniques applied in parallel, plus a business-legible
reference.

- **K-Means** on scaled RFM-LE, with *k* selected by silhouette and elbow.
- **Hierarchical clustering** with a dendrogram, as a structural cross-check on
  whether the eight business segments are natural or imposed.
- **PCA** for 2-D segment visualisation and to measure how much RFM-LE variance
  actually sits in two components.
- **Rule-based RFM-LE quintiles** as the reference the clusters are compared
  against. Where the rules and the clusters disagree, the disagreement is itself
  a dashboard insight.

**CLV:** `lifetimes` BG/NBD plus Gamma-Gamma, treating each **recharge as a
transaction**. The non-contractual, alive-or-dead-unobserved assumption behind
BG/NBD is literally true in prepaid, which makes this an unusually clean fit
rather than a borrowed one. The implementation is validated on UCI Online Retail
II before being pointed at recharges, and benchmarked against the IBM CLTV field.

**Role:** CLV is the **budget ceiling**. Hard rule: total retention spend on a
subscriber never exceeds a configurable fraction of predicted 12-month CLV,
default 15%. At 30 LYD ARPU that is roughly **54 LYD per subscriber per year** —
a meaningful budget against a catalogue where the primary retention instrument
costs 1 LYD. That single constraint is what makes the pricing engine defensible
to a CFO.

#### M3 — Dynamic Pricing & Off-Peak Offloading

Two mechanisms in one module, operating over the real 57-bundle catalogue.

**(a) Personalised price.** For bundle `b`, subscriber `i`:

```
P(i,b) = P_base(b) × ( 1 − d(i,b) )

d(i,b) = clip(
            w₁·ChurnRisk(i)                  ← urgency
          + w₂·LoyaltyIndex(i)               ← earned reward
          + w₃·PriceSensitivity(i,b)         ← elasticity
          − w₄·AffordabilityHeadroom(i)      ← don't discount those who can pay
          , 0 , d_max(tier(i)) )
```

| Tier | Qualification | `d_max` | Preferred instrument |
|---|---|---|---|
| Bronze | < 12 months tenure | 5% | Price discount |
| Silver | 12–36 months, regular recharge | 10% | Discount or bonus data |
| Gold | 36–84 months, high RFM-LE | 15% | **Morning pass** |
| Platinum | 84+ months or top value decile | 20% | **Morning pass + on-net minutes** |

The five Mix tiers map naturally onto this ladder, which is a convenience the
catalogue hands us: the operator has already built the product structure that a
loyalty ladder needs.

**(b) Off-peak offloading.** Peak-hour capacity is what drives network capex, so
shifting load has real avoided-capex value beyond the near-zero marginal cost of
an off-peak bit.

The anchor product is the operator's own 1 LYD morning pass, valid 06:00–11:00.
Using the published window rather than a detected one is not a compromise — it
is the answer, and it is better evidence than any trough the project could infer
for itself.

**A 1 LYD unlimited pass is a remarkably cheap retention instrument.** Granting
one costs less than discounting almost anything else in the catalogue, which is
why the engine reaches for it before considering a price cut. Value-add before
discount: a headline cut permanently reduces realised ARPU and is trivially
matched by a competitor; an off-peak grant is perceived as generous and leaves
the published price sheet intact.

**Cannibalisation guard.** This is the single most important commercial critique
of the idea, and it is answered in code rather than in a footnote. At 1 LYD for
unlimited data and voice across the working morning, the pass is cheap enough to
pull heavy users **down off a 35–75 LYD monthly Mix bundle** they were paying
for willingly. Eligibility therefore excludes subscribers whose peak usage would
simply shift rather than grow, the pass is granted as **additive rather than
substitutable**, and a simulated margin check runs before any cohort is
approved. §7.2 shows why this guardrail, not the margin floor, is the one that
decides whether the business case holds.

**The six guardrails**, enforced in code and asserted in required CI gates:

1. **Margin floor** — `P(i,b) ≥ variable_cost(b) × (1 + min_margin)`. No
   loss-making offer.
2. **CLV ceiling** — cumulative 12-month discount ≤ 15% of predicted CLV,
   checked against *trailing* spend rather than the current offer alone.
   Twelve individually-reasonable offers is the classic way this constraint gets
   defeated.
3. **Budget constraint** — cohort allocation solved as a knapsack / LP
   (`PuLP`): maximise expected retained margin subject to total incentive cost
   ≤ budget.
4. **Cannibalisation guard** — low churn risk *and* high value are excluded;
   the pass must be additive; simulated ARPU erosion capped at 2%.
5. **Fairness** — no pricing on protected or proxy-protected attributes.
   A post-hoc **distribution audit** across value deciles and tenure bands
   checks that discount spend is defensible. A gap there is *expected*, since
   loyalty tiers exist and `d_max` rises with tenure by design; what the audit
   catches is a gap wider than the published ladder explains, which is the
   signal that something other than the ladder is driving price.
6. **Auditability** — every decision persists inputs, weights, active
   constraints and reason codes to `decision_log`, replayable on demand.

Guardrails **re-check the final number** rather than trusting the pricing
function to have applied them, because a guardrail that only runs inside the
thing it constrains is not a guardrail. A breach raises; it does not clamp
silently.

#### M4 — Smart Advance: a learned limit for emergency credit

Neither product is new. Almadar already extends emergency airtime and emergency
data; what neither has is a risk model. This module replaces allocation rules
that gate on the subscriber being broke and then size the advance by
"consumption".

```
Limit(i) = min(
    f( PD(i) )              ← repayment probability, learned
  , g( LoyaltyTier(i) )     ← tier ceiling
  , h( CLV(i) )             ← never advance beyond recoverable value
  , affordability(i) )      ← what one typical top-up can actually clear
```

`PD(i)` comes from **two prediction heads sharing M1's feature pipeline** — one
per product, because the debt sizes and the eligible populations differ. Not
separate models with their own infrastructure. This is why M4 is cheap to build
despite being the most differentiated idea in the project.

Target: settled by the next recharge, censored at 14 days. Behavioural rather
than contractual, because neither product publishes a grace period.

**The airtime advance** is constrained to the operator's real denominations —
1, 3 and 5 LYD. The system cannot invent a 2 LYD advance, so the PD bands map
onto what actually exists. **The data advance** is flat 5 LYD, so the only
decision available is grant or decline; the PD threshold is therefore stricter,
because 5 LYD is a large debt against a 3 LYD card.

**The `affordability` term is the one the incumbent has no equivalent of**, and
it is the guard that catches the central finding. It uses the subscriber's
**modal** recharge, not their mean — the mean is inflated by a single
salary-week top-up they will not repeat, and using it would systematically
over-lend to precisely the subscribers this guard exists to protect.

**Safety guards, all mandatory:**

| Guard | Rationale |
|---|---|
| **Affordability ceiling** | Never issue a debt larger than one typical top-up clears. A 5 LYD debt against a habitual 3 LYD recharger is a trap, not a service. |
| **Chronic-distress exclusion** | Subscribers whose pattern shows sustained rather than temporary shortfall are excluded regardless of PD. Includes **alternation between the two products**, which the incumbent design cannot see. Repeatedly advancing to the most financially stressed subscribers is how digital credit has gone wrong elsewhere. |
| **Cooling-off period** | Minimum interval between advances, and monthly caps on count and cumulative exposure. The operator permits same-day repeat borrowing once the debt is cleared; the system does not, because that is a revolving credit line and this is not one. |
| **CLV-bounded exposure** | Never advance beyond a fraction of recoverable lifetime value. Re-checked on the final number, not the input. |
| **Lockout risk score** | A separate flag when the recommended advance carries meaningful probability of leaving unpaid debt at day 14 — which blocks re-subscription and locks the subscriber out of the service they reached for. The system's job is to prevent that outcome, not to optimise recovery after it. |
| **Affordable fallback** | Declining with nothing sends the subscriber away. Declining with the 0.5 LYD / 50 MB daily pack — which they *can* afford — is a service. |
| **Fee structure flagged for review** | Neither product documents a fee today. Any future fee is modelled as a **fixed charge, never time- or percentage-based**. Libya's financial framework makes interest a live question, and the structure is flagged for Shariah review rather than claimed resolved. |
| **Reject inference** | Repayment is only observed for subscribers who were granted an advance, and here the gate is *balance-based* — so the training population is filtered on being broke. The selection bias is sharper than in a normal credit setting, and the report documents it before applying a correction. |

**The headline insight for the pitch:** the cheapest emergency-credit failure is
invisible in the operator's own reporting. A 5 LYD data advance against a 3 LYD
smallest card cannot be cleared in one transaction; the debt persists; and
because re-subscription requires it cleared, the subscriber is locked out of the
service they reached for while a balance sits against the line. A flat rate
guarantees this happens to a predictable share of subscribers every month. A
learned limit is not a nice-to-have; it is a fix for a harm the current design
cannot detect.

### 3.3 The Retention Ladder: three stages of intent to leave

Not a separate module. A **delivery policy layer** over M1b and M3, which is why
it costs almost nothing to build.

Intervention intensity scales with how long the line has been cold, with two
refinements that most operators get wrong.

**Stage boundaries come from the hazard function, not from intuition.** Rather
than picking 7 / 30 / 60 days by feel, the Kaplan-Meier and hazard curves from
M1b identify where recovery probability falls sharply. Those inflection points
become the stage cut-points, recomputed per segment.

| Stage | Trigger | Intervention | Instrument |
|---|---|---|---|
| **1 — Cooling** | Recharge gap exceeds the subscriber's own baseline | Low-cost nudge | Reminder SMS, morning pass, advance-limit reminder |
| **2 — Cold** | Past the first hazard inflection | Peak spend | Personalised priced bundle from the Mix ladder, loyalty bonus, on-net pack if leakage detected |
| **3 — Dormant** | Past the second inflection | **Reduced spend** | Single low-cost win-back, then stop |

Stage 1 triggers on the subscriber's **own** baseline gap, not a global number. A
subscriber who normally recharges weekly is cooling at day 10; one who recharges
monthly is not.

**The inverted-U.** Most operators escalate the incentive as the line gets
colder, which is backwards. Recovery probability collapses faster than offer
value rises, so expected return per LYD spent peaks in the middle and falls
away. Optimal spend is low, then high, then **low again**. Stating this signals
an understanding of retention economics rather than retention mechanics.

**Sleeping-dogs guard.** Contacting a dormant-but-not-departing subscriber can
remind them to leave. The uplift model's negative-effect quadrant is excluded
from all three stages.

**Uplift method.** A two-model difference — treated response minus control
response — validated on Criteo's real randomised data and then applied here,
rather than a causal-inference library. At this data scale the additional
machinery buys precision we could not validate on generated response anyway, and
the simpler method is defensible in a three-minute pitch. That is a recorded
decision, not an omission.

---

## 4. User Interfaces & Deliverables

### 4.1 CVM Command Center (operator-facing)

Streamlit, four screens.

| Screen | Contents |
|---|---|
| **Executive Overview** | Subscribers at risk (30d), **revenue at risk in LYD**, base composition by tier, churn trend, unclearable-debts-avoided counter, retained-revenue simulation against a do-nothing baseline |
| **Segment Explorer** | RFM-LE heatmap, dendrogram from hierarchical clustering, PCA scatter of K-Means clusters, per-segment behaviour cards, and the cells where rules and clusters disagree |
| **Subscriber 360** | Lookup by hashed ID → churn probability from both arms, survival curve, RFM-LE scores, CLV, **SHAP waterfall in plain language**, recommended bundle with computed price, **advance limit with its binding constraint**, retention stage |
| **Campaign Builder** | Filter cohort → set LYD budget → uplift simulation → expected retained subscribers, cost, net margin → export targeting CSV. Shows **which guardrail bound and how many candidates each one rejected**, which is the most persuasive thing on the screen |

### 4.2 Subscriber Channel Simulator

A mock of the channels an Almadar prepaid customer actually uses: a **USSD menu
flow** including `*140#` airtime-credit and `*000#` emergency-data options, and
an **SMS preview**, in **Modern Standard Arabic with RTL rendering** and an
English toggle.

Entering a test subscriber shows the exact bundle, price and advance limit the
engine selected, with message copy generated from the engine's reason codes. The
LLM writes the *wording*; it never invents a price, a bonus or a limit, and if
the engine returned no offer the simulator shows no offer.

Arabic SMS is UCS-2 encoded — 70 characters, not 160 — so copy that fits in
English silently becomes two messages in Arabic. The simulator enforces the real
limit.

Low engineering cost, disproportionate demo impact. It collapses the distance
between "we built a model" and "here is what the customer receives."

### 4.3 Prediction & Decision API

FastAPI with auto-generated OpenAPI docs, Pydantic v2 contracts, structured
errors, `/health`. Single and batch modes. Target **p95 < 200 ms** on one CPU
container, verified with `locust` against the Cell2Cell holdout.

`/health` reports `ok` only when **every** model is loaded and the feature store
is readable. A partial deploy reports `degraded` and names what is missing,
because an API reporting `ok` with nothing loaded is worse than one reporting
nothing.

Identifiers are salted SHA-256 hashes throughout. There is no endpoint anywhere
that accepts a raw MSISDN; sending one returns 422.

### 4.4 Deliverables Checklist

| # | Deliverable | Acceptance criterion |
|---|---|---|
| D1 | Git repository | `docker compose up` reproduces the system from a clean clone |
| D2 | GAN synthesis engine | Passes the SDMetrics gate; seeded and reproducible; CTGAN vs TVAE vs Copula comparison reported |
| D3 | M1 benchmark report | LightGBM vs LSTM with calibration curves, PR-AUC, lift, and a written architecture verdict |
| D4 | Uplift validation | Method validated on Criteo's real randomised arms before application to the generated population |
| D5 | All trained models + MLflow runs | Params, metrics and artefacts logged for every experiment |
| D6 | FastAPI service | Live Swagger docs, p95 latency evidence |
| D7 | Command Center | Four screens functional on generated data |
| D8 | Channel simulator | Arabic RTL rendering verified, SMS length limit enforced |
| D9 | Technical report (~20 pp) | Methodology, results, honest limitations |
| D10 | Model cards | One per model: intended use, data, metrics, limitations, ethics |
| D11 | Data dictionary | Every field: type, source (real vs generated), generation logic |
| D12 | Market-facts register | Every commercial figure with a `confirmed` / `assumption` status and a source |
| D13 | Integration contract | Published endpoints, worked example, grounding rules for LLM consumers |
| D14 | 3-minute pitch deck + 5-minute demo video | Video doubles as live-demo insurance |

---

## 5. Tech Stack

Every component is free or open-source. Serving is CPU-only. One module trains
on a free GPU session.

### 5.1 Data Engineering

| Tool | Purpose |
|---|---|
| Python 3.11 | Runtime |
| pandas / **Polars** | Transformation; Polars for Cell2Cell-scale joins |
| **DuckDB** | Embedded analytical SQL — the feature store. No database server to operate |
| PyArrow / Parquet | Columnar storage, partitioned by snapshot date |
| NumPy | Sequence tensor construction for the LSTM |
| **Pandera** | Schema contracts and data-quality assertions in CI |
| **SDV** (CTGAN, TVAE, GaussianCopula) | Adversarial and classical synthesis |
| **SDMetrics** | Synthetic fidelity gate |
| Faker | Locale-aware categorical fields |

### 5.2 Modelling

| Tool | Purpose |
|---|---|
| scikit-learn | Pipelines, preprocessing, calibration, Decision Tree, Naïve Bayes, KNN, SVM, K-Means, hierarchical clustering, PCA, metrics |
| **LightGBM** / XGBoost / CatBoost | Gradient-boosted ensembles |
| imbalanced-learn | SMOTE / ADASYN comparison arm |
| **lifelines** / scikit-survival | Cox PH, Random Survival Forest, Kaplan-Meier |
| **lifetimes** | BG/NBD + Gamma-Gamma CLV |
| **scikit-uplift** | Hillstrom loader and uplift evaluation curves |
| **SHAP** | Global and local explainability |
| **Optuna** | Hyperparameter search, 50 trials max per model |
| **PuLP** / scipy.optimize | Budget-constrained allocation |
| **TensorFlow / Keras** | LSTM benchmark arm; TensorBoard for training curves |

### 5.3 Serving & Frontend

| Tool | Purpose |
|---|---|
| **FastAPI** + Uvicorn | Inference and decision API |
| Pydantic v2 | Request/response validation |
| joblib / SavedModel | Model loading |
| APScheduler | Nightly batch scoring |
| DuckDB | Decision log and campaign store |
| locust | Latency and throughput testing |
| **Streamlit** | Command Center and channel simulator |
| Plotly / Altair | Interactive charts |
| arabic-reshaper + python-bidi | Arabic RTL rendering |

No agent framework, no vector store, no transformer models. The component
publishes an API; it does not host a conversational surface. That keeps the
install roughly 4.5 GB smaller and removes an entire class of dependency risk.

### 5.4 MLOps & Quality

| Tool | Purpose |
|---|---|
| **MLflow** | Experiment tracking and model registry across all modules |
| **Evidently AI** | Data and prediction drift reports |
| pytest + pytest-cov | Unit and integration tests, including guardrail and leakage gates |
| ruff + black + pre-commit | Lint and format gates |
| **GitHub Actions** | CI: lint → tests → schema checks → **leakage gate** → **guardrail gate** → privacy scan → build |

The leakage and guardrail jobs are **separate required CI jobs** rather than
part of a general test run, so they produce their own red/green signal. They are
the two gates the project commits to never cutting.

### 5.5 Deployment & Compute Budget

| Resource | Cost | Purpose |
|---|---|---|
| **Docker + Docker Compose** | Free | One-command reproducible stack |
| **Oracle Cloud Always Free** (4 ARM cores, 24 GB RAM) | **$0** | Always-on demo host. Comfortably runs the full CPU stack |
| **Hugging Face Spaces** free tier | **$0** | Public Streamlit demo, backup host |
| **Google Colab free T4** | **$0** | LSTM training (M1 Arm B) |
| LLM inference credits | ~$0–10 | Optional: Arabic offer copy in the channel simulator. Falls back to templated text |
| **Total** | **$0–20** | |

**Explicitly not purchased:** rented GPU servers, managed Kubernetes, managed
databases, any per-hour GPU instance, any hosted vector database. "We built,
trained and deployed all of this for under twenty dollars" is itself a pitch
line.

---

## 6. Execution Plan — 3 Weeks

### 6.1 Work Streams

| Stream | Scope |
|---|---|
| **Data** | Layers 1–3: ingestion, schema contracts, hashing, CTGAN synthesis, DuckDB feature store, sequence tensors, data dictionary |
| **Risk** | M1 both arms, survival, M4 repayment PD heads |
| **Value** | M2 clustering / PCA / CLV, CLV validation on Online Retail II |
| **Decision** | M3 pricing and off-peak engine, uplift validation on Criteo, guardrails, FastAPI, Docker, CI |
| **Frontend** | Command Center, channel simulator |
| **Quality & Product** | Evaluation harness, model cards, market-facts register, business case, pitch |

Working agreement: daily 15-minute stand-up, trunk-based development with PR
review, hard integration checkpoint at the end of each week.

### 6.2 Sprint Schedule

**Week 1 — Foundations (Days 1–5)**
*Goal: real data flowing, a classical baseline, the schema locked, GPU environment proven.*

| Day | Milestone |
|---|---|
| 1 | Repo scaffold, Docker skeleton, CI green. All datasets downloaded and licences recorded. GPU session provisioned |
| 2 | EDA on all three tabular datasets. UCI deduplication done and the count recorded. Leakage audit of `Customer Value` |
| 3 | **Schema v1 frozen** — every generated field named, typed and justified against the market-facts register. API contracts frozen. CTGAN training begins |
| 4 | Synthesis engine v1 produces 100k subscribers. SDMetrics gate run. CTGAN vs TVAE vs Copula comparison logged. RFM-LE scoring implemented |
| 5 | ⚑ **Checkpoint 1:** baseline LightGBM with honest temporal-split metrics. DuckDB feature store live. **Sequence tensors built.** API returns a stub score |

**Week 2 — Models (Days 6–10)**
*Goal: every model trained and reachable over HTTP.*

| Day | Milestone |
|---|---|
| 6 | M1 Arm A tuned and calibrated with SHAP working. **Arm B: LSTM built and first training run.** M2 K-Means and hierarchical clustering complete |
| 7 | **LSTM tuned; benchmark table produced.** Cox survival model. CLV validated on Online Retail II, benchmarked against IBM CLTV. PCA visualisation |
| 8 | **Uplift method validated on Criteo**, warmed up on Hillstrom. **M3 pricing engine v1** with all six guardrails and unit tests |
| 9 | **M4 both PD heads trained.** Affordability ceiling and all safety guards implemented and tested. Lockout-risk scoring |
| 10 | ⚑ **Checkpoint 2 — feature freeze.** All endpoints live. Command Center screens 1–3 rendering real output. Anything not working by end of Day 10 is descoped, not rescued |

**Week 3 — Integration & Pitch (Days 11–15)**
*Goal: a system that survives a live demo and a story that survives an evaluator's questions.*

| Day | Milestone |
|---|---|
| 11 | Campaign Builder screen with guardrail-rejection counts. Retention ladder boundaries derived from hazard curves |
| 12 | Channel simulator with Arabic RTL and SMS length enforcement. **Integration test with the Chatbot and Copilot owners against the published contract** |
| 13 | Hardening: latency test (p95 < 200 ms), Evidently drift report, full guardrail suite, error handling. Business case finalised |
| 14 | Documentation sprint: technical report, model cards, market-facts register, README. **Demo video recorded** |
| 15 | ⚑ **Checkpoint 3:** pitch deck finished, three timed dry-runs, deployment verified from a clean machine |

### 6.3 Descoping Ladder

Agreed in advance so that cutting scope is a decision rather than a panic. Cut
strictly in this order:

1. KKBox ingestion → Cell2Cell alone carries the sequence arm
2. Hierarchical clustering → K-Means and PCA alone carry the segment screen
3. Random Survival Forest challenger → Cox PH alone
4. Optuna tuning → sensible fixed hyperparameters
5. Evidently drift report → schema contracts alone

**Never cut:** the M1 LightGBM-vs-LSTM benchmark, M1 calibration, the M3
guardrails, the M4 safety guards, the uplift validation on Criteo, the holdout
control group, the leakage gate, the data dictionary, the market-facts register,
or the honest-metrics disclosure. The benchmark and the guardrails are the
project's technical and ethical core respectively.

### 6.4 Risk Register

| Risk | L | I | Mitigation |
|---|---|---|---|
| LSTM underperforms and it is treated as failure | H | M | Reframed in advance: the benchmark is the deliverable, not the winner. Both outcomes are written up as results |
| Generated data too clean, models look unrealistically good | H | H | SDMetrics detection gate; deliberate noise and missingness injection; naive and honest metrics both reported with the gap explained |
| Inflated metrics from duplicates or leaky features | H | H | Automated leakage gate in CI; mandatory temporal splits; `Customer Value` excluded; label artefacts and drivers separated explicitly |
| Cannibalisation swamps the retention gain | M | H | Quantified in §7.2; simulated margin check before cohort approval; ARPU-erosion cap set below the break-even rate |
| Bundle cost estimates wrong, so margin figures mislead | M | M | Labelled as estimates everywhere they appear; margin reported as a ratio against a stated assumption, never as an audited figure |
| GPU session limits disrupt LSTM training | M | M | Checkpoint every epoch; the model is small enough to finish inside one session; CPU fallback available |
| Integration failure in the final week | M | H | API contracts frozen Day 3; stub endpoints from Day 5; contract test with consuming components on Day 12, not during integration week |
| Live demo failure at pitch time | M | H | Pre-recorded 5-minute video; local Docker fallback; no dependency on venue Wi-Fi |
| Scope creep | H | M | Descoping ladder agreed Day 1; Day-10 freeze non-negotiable; scope boundaries in §1.4 stated as boundaries, not preferences |

### 6.5 Ethics, Privacy & Compliance

Prepaid CVM touches pricing, credit and behaviour, which is the exact
combination where algorithmic systems cause harm. Explicit commitments:

- **No real subscriber data.** Every record is public-research or generated.
  Identifiers are SHA-256 with salt from the moment of ingestion; no raw MSISDN
  exists in the repository at any point. CI scans for MSISDN patterns and fails
  the build on a match.
- **Data residency.** The architecture assumes real records never leave operator
  infrastructure. The deployable artefact is the container, not a data export.
- **Credit is capped, not maximised.** M4 optimises for subscriber solvency and
  continued access, not recovery yield. The affordability ceiling,
  chronic-distress exclusion and cooling-off periods are mandatory, not
  configurable.
- **Declining is a service.** A subscriber who cannot safely take a 5 LYD
  advance is offered the 0.5 LYD pack they *can* afford, not silence.
- **Fee structure flagged, not assumed resolved.** Any future service fee is
  modelled as a fixed charge and referred for Shariah review.
- **No protected-attribute pricing.** Age group may inform offer *relevance*,
  never price. A post-hoc distribution audit checks that discount spend across
  value and tenure bands stays within what the published loyalty ladder
  explains.
- **No LLM in any path that moves money.** The component contains no agent and
  no LLM call in any decision path. Consuming components read from the decision
  engine and explain it; they cannot alter it.
- **Full auditability.** Every pricing and advance decision logs inputs,
  weights, active constraints and reason codes, and is replayable.
- **Transparency to the customer.** Every offer carries a human-readable reason
  — "loyalty reward, six years with us" — not an opaque personalised price.
- **Honest claims.** The report states that generated-population metrics are not
  evidence of production performance, distinguishes the uplift method validated
  on real randomised data from the population it is applied to, labels every
  commercial estimate, and specifies the real-data validation path required
  before any deployment decision.

---

## 7. Indicative Business Case

All figures are **illustrative**, built on the stated assumptions in §2.3, and
shipped as a spreadsheet so evaluators can change any input. The method is the
point, not the number.

**Assumptions (pilot slice):** 1,000,000 addressable prepaid subscribers ·
30 LYD monthly ARPU · 3.5% monthly silent churn (~35,000) · model captures ~62%
of churners in the top 3 deciles · 120,000 treated per monthly campaign · 10%
untreated control · 1.5 LYD blended incentive, reflecting a mix of the 1 LYD
morning pass and larger discounts on Mix bundles.

### 7.1 Retention campaign

| Line | Value |
|---|---|
| Monthly revenue at risk | 35,000 × 30 LYD = **1,050,000 LYD** |
| Treated cohort | 120,000 |
| Assumed uplift (treatment − control) | 2.5 pp → **3,000 additional retained** |
| Retained value, 12-month horizon | 3,000 × 30 × 12 = **1,080,000 LYD** |
| Campaign cost @ 1.5 LYD blended incentive | **180,000 LYD** |
| **Net contribution** | **900,000 LYD · ROI ≈ 6.0×** |

**Sensitivity — ROI (benefit ÷ cost):**

| | Cost 1.0 LYD | Cost 1.5 LYD | Cost 3.0 LYD |
|---|---|---|---|
| **Uplift 1.0 pp** | 3.6× | 2.4× | 1.2× |
| **Uplift 2.5 pp** | 9.0× | 6.0× | 3.0× |
| **Uplift 4.0 pp** | 14.4× | 9.6× | 4.8× |

**Note what this table does not contain: a loss-making cell.** At 30 LYD ARPU
against a 1–3 LYD instrument, the incentive arithmetic is simply robust — even
a 1 pp uplift at triple the assumed cost returns 1.2×. Presenting that as the
main risk would be flattering the proposal.

The real fragility is elsewhere, and §7.2 is where it lives.

### 7.2 Cannibalisation — the risk that actually decides this

The morning pass costs 1 LYD for unlimited data and voice across 06:00–11:00.
The monthly Mix tiers run 20–75 LYD. If granting the pass persuades a heavy user
to **stop buying a monthly bundle**, the ARPU loss dwarfs the incentive saving.

| Line | Value |
|---|---|
| Monthly retained value from the campaign | 1,080,000 ÷ 12 = **90,000 LYD/month** |
| ARPU loss per subscriber who downgrades off a 35 LYD monthly | **34 LYD/month** |
| Downgraders that erase the entire gain | 90,000 ÷ 34 ≈ **2,650** |
| As a share of the 120,000 treated cohort | **≈ 2.2%** |

**Cannibalisation above roughly 2.2% of the treated cohort wipes out the whole
retention gain.** At 5% it turns the campaign firmly negative.

This is why the cannibalisation guard — not the margin floor — is the guardrail
that matters most on this price sheet, and why `max_simulated_arpu_erosion` is
set at **2%**, just below the break-even rate. The guard excludes low-risk
high-value subscribers, requires the pass to be additive rather than
substitutable, and runs a simulated margin check before any cohort is approved.

Stating this openly is a stronger position than hiding it: it demonstrates that
the commercial risk was identified, quantified, and constrained in code.

### 7.3 Avoided waste — the larger prize

A blanket campaign across the full base at the same 1.5 LYD incentive costs
**1,500,000 LYD per month** for comparable or worse uplift, because most of the
spend lands on subscribers who would have recharged regardless. Targeted
selection saves roughly **1,320,000 LYD per month in wasted incentive**.

In prepaid CVM, *not* spending is usually worth more than spending better.

### 7.4 Prevented service lockouts

The mechanism from §1.2 P5, quantified. Every step is an assumption and is
labelled as one; the chain is what matters.

| Line | Value |
|---|---|
| Monthly emergency-credit users | ~150,000 |
| Of which نت في وقته (data, 5 LYD) | ~50,000 |
| Share whose modal recharge is the 3 LYD card | ~26% → **13,000 unclearable debts** |
| Persisting to lockout | ~30% → **3,900 locked out** |
| Churning within 90 days of lockout | ~20% → **780 subscribers** |
| Remaining 12-month value each (30 × 12) | 360 LYD |
| **Monthly loss from unclearable advances** | **~281,000 LYD** |
| Avoidable by declining and offering the 0.5 LYD fallback (~60%) | **~168,000 LYD per month** |

This is harm the current design cannot see, because the operator's reporting
records the debt as outstanding rather than the subscriber as excluded. It is
also the cheapest thing in this proposal to fix: the facility, the billing
integration and the recovery mechanics all exist already. **Only the
limit-setting logic changes.**

---

## 8. Evaluation & Pitch Highlights

### 8.1 The Four Points to Land

**① Localisation is a technical contribution, not a coat of paint.**
Most capstone churn projects train on a US postpaid dataset with a "Contract
Type" column and call it telecom AI. Libya is overwhelmingly prepaid: no
contract, no cancellation, no churn event. We **redefined the target variable**
(30 days of zero revenue-generating events), **redefined RFM** for a market with
no purchase transactions, engineered a **dual-SIM leakage detector** from the
incoming-to-outgoing call ratio, and priced everything against the operator's
**real 57-bundle catalogue and published tariffs** — including a block-rate
voice tariff that makes call length, not call volume, the driver of revenue per
minute. This problem cannot be solved by downloading a Kaggle notebook.

**② We found a harm the operator's own reporting cannot see.**
Almadar's emergency data advance costs 5 LYD. The smallest recharge card sold is
3 LYD. A subscriber whose habitual top-up is the smallest card cannot clear that
debt in one transaction — and because re-subscription requires it cleared, they
are **locked out of the service they reached for**. Both emergency products gate
on the subscriber being nearly out of money, allocate by "consumption" rather
than repayment probability, and are mutually exclusive, so subscribers in
sustained difficulty alternate between them unobserved. We replace the flat rate
with a learned limit bounded by repayment probability, loyalty, lifetime value
**and what one typical top-up can actually clear**. Roughly 168,000 LYD a month,
from logic changes alone.

**③ The most valuable product in the catalogue was already there.**
The operator sells a 1 LYD pass for unlimited data and voice between 06:00 and
11:00. That tells us they have already identified and priced their own spare
capacity, and exactly when it is. So the off-peak strategy is not a proposal —
it is the personalisation of an existing product, which is a much stronger claim.
It also means we had to answer the hard question honestly: a 1 LYD unlimited
pass is cheap enough to cannibalise a 35 LYD monthly bundle, and we can show
that **above 2.2% downgrade rate the entire retention gain disappears.** The
guardrail threshold is set below that break-even, in code, before any cohort
ships.

**④ Intellectual honesty as a differentiator.**
Published work on our primary dataset reports ~97% accuracy and ~0.99 AUC. We
reproduce those numbers and then show they are **wrong**: inflated by ~300
duplicate rows and by a pre-computed `Customer Value` field that leaks the
outcome. We deduplicate, drop the leaky feature, split temporally, and report
the lower honest figures alongside the naive ones. We separate the label's
behavioural *drivers*, which the model legitimately sees, from its *artefacts*,
which it must never see — and we test both directions, because over-tightening
that control is as damaging as under-tightening it. We validate the uplift
**method** on 25 million real randomised rows and are explicit that the
population it is applied to is generated. **We would rather show a defensible
0.78 PR-AUC than an indefensible 0.99.**

### 8.2 Three-Minute Pitch Structure

| Time | Beat | Content |
|---|---|---|
| **0:00–0:20** | Hook | "In Libya, customers don't churn. They just stop topping up. About 1.05 million dinars a month walks out silently." |
| **0:20–0:45** | The twist | "And their emergency credit has a bug nobody can see. The data advance costs five dinars. The smallest recharge card is three. If that's the card you buy, you can never clear the debt — and until you do, you're locked out of the service you reached for." |
| **0:45–1:35** | **Live demo** | Subscriber 360: one hashed ID → risk from both arms, survival curve, SHAP explanation in plain language, recommended bundle from the real catalogue with its computed price, advance limit **with the constraint that set it**. Then Campaign Builder: set a budget, watch the guardrails reject candidates and say why |
| **1:35–2:20** | Technical depth | CTGAN population gated by an adversarial detection test. LightGBM vs LSTM with the honest verdict. Uplift validated on 25M real randomised rows. Calibrated probabilities into constrained optimisation with margin, CLV, budget and cannibalisation guardrails |
| **2:20–2:45** | Commercial case | ROI ≈ 6× with the sensitivity table. 1.32M LYD/month in avoided waste. 168k LYD/month in prevented lockouts. And the number that shows we did the work: **2.2% cannibalisation wipes it all out, so the guard is set at 2%** |
| **2:45–3:00** | Close | "Real catalogue, real tariffs, real credit products. One command to run it, under twenty dollars to build it, and every number in the deck has a source or a label saying it doesn't." |

### 8.3 Anticipated Evaluator Questions

| Question | Prepared answer |
|---|---|
| *"Your population is generated — how do we know it works?"* | Three separate answers. The *structure* is learned adversarially from three real telecom datasets and gated by a discriminator detection test. The *prices* are the operator's real published catalogue and tariffs, not invented. The *uplift method* is validated on 25 million rows of real randomised treatment and control before it ever touches generated data. What remains generated is the population, and we say so. |
| *"Why isn't everything deep learning?"* | We benchmarked it. On tabular telecom data gradient boosting matched or beat the LSTM at a fraction of the compute, and SHAP gives regulator-grade explanations. We report whichever arm won and explain why. |
| *"How can you train on a label you generated yourself?"* | Carefully, and the code makes the distinction explicit. The hazard is a function of observable behaviour, so the signal is recoverable — that is deliberate, because a model that can see no driver of its label has nothing to learn. What it never sees are the label *artefacts*: the hazard score, the churn date, the label itself. Both directions are tested. And we state plainly that this demonstrates the pipeline works, not that the model would perform this way in production. |
| *"Isn't a 1 LYD unlimited pass going to destroy your ARPU?"* | It could, and we quantified exactly when: above a 2.2% downgrade rate on the treated cohort, the entire retention gain disappears. That is why the cannibalisation guard excludes low-risk high-value subscribers, requires the pass to be additive, runs a simulated margin check before approval, and caps modelled ARPU erosion at 2% — below break-even. |
| *"How is this different from any churn project?"* | Churn prediction is one of four modules. The product is the pricing, offer and credit-limit decision, with uplift targeting and margin guardrails over a real 57-bundle catalogue. And we found a harm in the operator's own credit product that its reporting cannot detect. |
| *"Where do your bundle costs come from?"* | They are estimates — 25% of price for metered data, 35% for unlimited — and they are labelled as estimates everywhere they appear, because the operator's marginal cost of a gigabyte is not public. The margin floor needs a figure to enforce; what we owe you is the disclosure, which is in the market-facts register. |
| *"Why doesn't your model use location?"* | Because we could not do it honestly. Network planning and cell anomaly detection belong to another component of this platform; duplicating them here would mean two teams maintaining two answers to the same question. Service quality still matters and still enters the model — as a per-subscriber feature drawn from real measured data, not as a map we invented. |
| *"What breaks first at scale?"* | The feature store. DuckDB is correct at demo scale; at millions of subscribers it becomes a columnar warehouse with the same schema. Models and decision logic are unchanged, because nothing above the feature layer knows what the store is made of. |
| *"Is personalised pricing fair?"* | Only upward: discounts and bonuses, never surcharges. No protected attributes. A post-hoc audit checks discount spend across value and tenure bands stays within what the published loyalty ladder explains. Full decision audit log, and a human-readable reason on every offer. |
| *"Is the emergency credit ethical?"* | It is the reason we built an affordability ceiling, chronic-distress exclusion, cooling-off periods and CLV-bounded exposure. The objective function is subscriber solvency, not recovery yield — and when we decline, we offer the cheapest thing they can actually afford instead of nothing. |

---

## Appendix A — Dataset Quick Reference

| ID | Dataset | Size | Access | Licence | Role |
|---|---|---|---|---|---|
| A | Iranian Churn (UCI 563) | 3,150 | `fetch_ucirepo(id=563)` | CC BY 4.0 | Primary: prepaid, MENA, call-failure feature |
| B | Cell2Cell (Duke/Teradata) | 71,047 | Kaggle `jpacse/datasets-for-churn-telecom` | public research | Scale, trend features, LSTM viability |
| C | IBM Telco Churn | 7,043 | IBM sample / Kaggle mirrors | public sample | CLTV benchmark, fast baseline |
| F | Criteo Uplift | 25M | `ailab.criteo.com` / HuggingFace | academic use | **Real randomised uplift validation** |
| G | Hillstrom MineThatData | 64,000 | `sklift.datasets.fetch_hillstrom` | public | Uplift warm-up, sleeping-dogs demo |
| H | KKBox WSDM | ~1M members | Kaggle competition | competition rules | Real daily sequences, no-renewal label |
| J | UCI Online Retail II | 1,067,371 | `fetch_ucirepo(id=502)` | CC BY 4.0 | BG/NBD + Gamma-Gamma validation |

Operator commercial data — catalogue, tariffs, recharge ladder and both
emergency-credit products — is transcribed from Almadar's published material
into `conf/catalogue.yaml` and `conf/market.yaml`, with per-field provenance.

## Appendix B — Integration Contract

Published endpoints. Frozen; anything not listed is internal.

| Endpoint | Method | Purpose |
|---|---|---|
| `/v1/cohort/query` | POST | Filter a population → hashed IDs + aggregate at risk |
| `/v1/score/churn` | POST | Calibrated churn probability, optional time-to-churn |
| `/v1/subscriber/{id}` | GET | Full 360 view for one subscriber |
| `/v1/offer/next-best` | POST | Recommended bundle, priced and guardrailed |
| `/v1/price/quote` | POST | Price one specific bundle |
| `/v1/advance/limit` | POST | Learned emergency-credit limit, per product |

**Two rules on every call.** Identifiers are salted SHA-256 hashes — 64
lowercase hex characters, and a raw MSISDN returns 422. And everything is
read-only: `/v1/offer/next-best` *computes* an offer, it does not send one.

**What CVM needs from Component 2**, keyed by `subscriber_id_hashed` and
refreshed daily: `dropped_call_rate_30d`, `data_session_failure_rate`,
`service_outage_hours_30d`. Until that exists, the synthesis engine generates
the same field names, so swapping the source changes nothing in M1. The cell →
subscriber join belongs on the network side, where the cell data lives.

**Grounding rules for LLM-based consumers**, which are project commitments
rather than suggestions:

1. The LLM never sets a price, a bonus or a credit limit. It reads the numbers
   this API returns and explains them.
2. Never invent a number. If the API did not return it, it does not go in the
   answer.
3. Cite the tool output. Every claim traces to a response field, and the
   tool-call trace is visible in the UI.
4. Refuse rather than guess. "I could not determine that" beats a confident
   wrong answer.
5. Never expose a raw identifier, even if you hold one.
6. Do not cache decisions. Prices and limits are recomputed against current
   guardrails and budget; a cached offer may violate a constraint that has since
   bound.

Safe to index for retrieval: the model cards, the data dictionary, the
architecture document, the market-facts register, and the pricing and advance
guardrail configs. Re-index whenever a guardrail changes, or the agent will cite
a rule the system no longer applies.

## Appendix C — Definition of Done

A module is complete only when it: (1) has unit tests in CI; (2) is reachable
through the API; (3) is visible in the UI; (4) is logged in MLflow with metrics;
(5) has a model card or data-dictionary entry; (6) has every commercial figure
it depends on recorded in the market-facts register with a provenance status;
and (7) survives `docker compose up` from a clean clone on a machine that is not
the author's.

Point 7 is the one that catches people.
