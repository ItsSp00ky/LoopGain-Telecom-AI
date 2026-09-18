# Market questions — Almadar Aljadid

Status board for the domain facts the synthesis engine needs. Answers live in
[`conf/market.yaml`](../conf/market.yaml) and
[`conf/catalogue.yaml`](../conf/catalogue.yaml).

**Operator: Almadar Aljadid (المدار الجديد), MCC/MNC 606-01.** Libyana is
modelled only as the competitor that dual-SIM leakage flows toward.

| | Count | |
|---|---|---|
| **Confirmed** | 8 | Q1 recharge · Q2 tariffs · Q3 catalogue · Q3b volumes · Q4 off-peak · Q5 zero-rating · Q6 emergency credit · Q10 language |
| **Decided estimate** | 1 | Q7 base and economics — ARPU 40 LYD, dual-SIM 85% |
| **Scope decided** | 2 | Q8 weekend kept · Q9 geography dropped, network quality kept |
| **Open** | 1 | Q6b partial-recharge settlement behaviour (minor) |

**Every question is answered.** Nothing blocks the synthesis engine.

---

## ✅ Answered

### Q1 — Recharge denominations · **confirmed**

**5 / 10 / 20 / 40 / 100 LYD.**

In `conf/market.yaml#recharge`. Two consequences worth knowing:

- The **5 LYD floor** is load-bearing for M4, because the نت في وقته data
  advance also costs **exactly 5 LYD**. A subscriber whose modal top-up is the
  smallest card can clear that debt and receives *nothing* for it: the whole
  card goes to the debt and they are back at a zero balance. That equality is
  the structural finding the M4 argument rests on.
- The cheapest data bundle is **0.5 LYD** (نت 50MB), so monetary fields must
  not be rounded to whole dinars anywhere in the pipeline.

*Still an assumption:* the **popularity split** across those five values. The
ladder is confirmed; the weighting is our guess. Any recharge agent could
answer this in thirty seconds — worth asking.

### Q3 — Bundle catalogue · **confirmed**

**37 bundles across 12 families**, from `Almadar/internet_offers_data_v4.csv`,
now structured in [`conf/catalogue.yaml`](../conf/catalogue.yaml).

Families: Golden and Silver unlimited, daily / weekly / monthly data, 5G
monthly and hourly, Macchiato hourly unlimited, Social, Elite, Family share,
and the morning off-peak pass.

Voice minutes appear in only two families -- the morning pass (unlimited) and
the shared Family plans. That makes the morning pass the primary **voice**
instrument as well as the off-peak data one, which matters for any subscriber
showing voice leakage.

This is far better than expected — M3 now prices real products.

### Q4 — Off-peak bundle · **confirmed, and it is not what we assumed**

**عروض الصبح — 1 LYD, unlimited data AND unlimited voice, valid 06:00–11:00.**

The off-peak window is the **morning**, not the night. Three things follow:

1. **M3 personalises an existing product** rather than proposing a new one.
   Materially stronger position in a Q&A.
2. The operator **has already priced its own spare capacity and told us when it
   is.** That is unusually strong evidence for a trough assumption — we are not
   guessing at 03:00 and hoping.
3. A 1 LYD unlimited pass is an extremely cheap retention instrument, which is
   why `conf/pricing.yaml` now reaches for it before any price cut.

It also *sharpens* the cannibalisation guard. At 06:00–11:00 the pass covers
the commute and the working morning — real usage for a lot of people — so the
risk of pulling someone down off a 35–80 LYD monthly bundle is genuine, not
theoretical.

### Q6 — Emergency credit · **confirmed, two products**

From `translated_service_details.md` and
`translated_internet_service_details.md`:

| | رصيد في وقته | نت في وقته |
|---|---|---|
| Type | Airtime advance | Emergency data |
| Access | `*140#`, `*140*5#` | `*000#`, Almadar app |
| Amounts | **1 / 3 / 5 LYD** | **flat 5 LYD** (2 GB, 3 days) |
| Gate | balance ≤ 0.5 LYD | balance ≤ 1 LYD **and** quota < 250 MB |
| Allocation | "according to consumption" | none — same for everyone |
| Settlement | first recharge; auto-settle check at 48 h | first recharge or transfer in |
| Repeat | same day, once debt cleared | once debt cleared |

> ### ⚠ This invalidates part of the original proposal
>
> The proposal's headline finding was built on **Libyana's** Credit Loan: a
> 12-month tenure gate, a 7-day grace period, degradation to "recharge stage",
> and eventual line reset and resale — "the operator is causing hard churn".
>
> **None of that transfers to Almadar.** There is no tenure gate, no published
> grace period, and no documented line-reset mechanism. Continuing to claim it
> would be fabricating the project's central finding.
>
> `conf/advance.yaml` now carries the replacement argument, which comes
> straight out of Almadar's own numbers and is arguably sharper:
>
> - **Both products gate on the subscriber being broke.** That is the inverse
>   of a risk filter — the eligible population is by construction the one least
>   able to repay.
> - **"According to consumption" is not a risk model.** A heavy user in decline
>   consumes a lot and repays badly; the rule cannot tell them apart from a
>   heavy user who is fine. The thresholds are not published.
> - **The data advance has no tiering at all.** 5 LYD for everyone.
> - **5 LYD debt > 3 LYD smallest card.** A small-card recharger cannot clear
>   it in one top-up, the debt persists, and because re-subscription requires
>   the debt cleared, they are **locked out of the service they reached for**.
> - **The two products are mutually exclusive**, so distressed subscribers
>   alternate between them — a pattern nothing in the current design watches.

**Small gap remaining (Q6b):** what happens on a *partial* recharge? If someone
with a 5 LYD debt tops up 3 LYD, is the debt part-settled, or does it stay
whole until covered? This changes the M4 label definition, so it is worth
confirming.
### Q2 — Pay-as-you-go tariffs · **confirmed**

Source: `Almadar/Pay-as-you-go tariffs.md`. Quoted in dirham; 1000 dirham = 1 LYD.

| | LYD |
|---|---|
| Almadar → Almadar voice | **0.090 for the first 3 minutes**, then 0.050/min |
| Almadar → Libyana voice | 0.090/min |
| Almadar → landline | 0.040/min |
| SMS, on-net **and** off-net | 0.050 |
| SMS international | 0.250 |
| Data (Bjawak) | 0.025/MB |
| Voice international | **not published** — left null, not guessed |

Three consequences, all now encoded in `conf/market.yaml#payg`:

1. **On-net voice is a 3-minute block, not a flat rate.** A 1-minute call costs
   0.090 LYD; a 10-minute call costs 0.440 LYD, or 0.044/min. Short calls are
   expensive and long ones cheap, so generated call *lengths* drive revenue per
   minute. Flattening this to a single rate would misprice most of the base.
2. **There is no on-net SMS discount** — 0.050 either way. SMS is therefore not
   a competitive lever, and any leakage feature built on SMS on/off-net mix
   would be noise. `conf/features.yaml` excludes it by name, with the reason.
3. **PAYG data is ~25× the bundle rate** (25 LYD/GB versus ~1 LYD/GB on the
   80 GB monthly). That promotes `bundle_vs_payg_share` from a ratio to a
   targeting feature: a subscriber on PAYG data is either unaware of bundles or
   cannot afford one up front. Those are different problems needing different
   offers, and M3 should not send the same thing to both.

### Q3b — Bundle volumes and costs · **resolved**

`نت ساعة 1_5G` and `نت ساعتين 2_5G` are **unlimited within the hour**, not
volume-capped. Updated in `conf/catalogue.yaml`.

`variable_cost_lyd` **stays as an estimate** — 25% of price for metered data,
35% for unlimited. Confirmed decision. The margin floor needs something to
enforce, and the obligation is to label the estimate rather than remove it. Say
so in the report; a stated margin must not look audited when it is not.

### Q5 — Zero-rated apps · **confirmed: none**

All traffic consumes allowance. The Social family (1 / 5 / 20 LYD) is a real
bundle rather than a zero-rating arrangement, so `social_bundle_share` stays a
meaningful feature.

### Q7 — Base and economics · **decided estimate**

| | Value | Note |
|---|---|---|
| Addressable prepaid subscribers | 1,000,000 | |
| **Monthly ARPU** | **40 LYD** | |
| Monthly silent churn | 3.5% | |
| **Dual-SIM penetration** | **85%** | |
| **Blended incentive** | **5 LYD** | |

ARPU is anchored on the product structure rather than guessed. نت 20 at 35 LYD
is the **base** monthly — what a subscriber needs for all-day data — and the
ladder runs well above it. An ARPU below the base bundle would imply most of
the base does not hold one, which the catalogue's shape contradicts.

**Two numbers follow and are used throughout:** 12-month value per subscriber
**480 LYD**, CLV ceiling (15%) **72 LYD**. Revenue at risk is 35,000 × 40 =
**1.4M LYD/month**.

**The 5 LYD blended incentive is the consequential one.** It is a mix, not a
single instrument: mostly 1 LYD morning passes, some bonus-MB grants, and a
smaller number of percentage discounts on bundles at the top of the ladder. It
sets a hard floor under M3, because expected value is positive only above

    break-even uplift = 5 / 480 = **1.04 pp**

Below that, treating loses money no matter how high the churn score is. The
decision engine enforces exactly this, and the business case is built on it.

**Dual-SIM at 85% changes the emphasis of the whole churn model.** At that level
dual-SIM is the norm, not a segment: "active" tells you almost nothing, and
`incoming_outgoing_ratio` goes from a clever extra feature to the central one.
Worth leading with in the pitch.

These remain estimates, not operator figures, and are labelled as such.

### Q10 — Language · **confirmed: MSA**

Modern Standard Arabic for all customer-facing copy. Dialect would read as more
authentic to a Libyan audience, but MSA is understood everywhere and is safer if
the evaluators are not Libyan.


---

## ✅ Scope decisions — both settled

Two scope calls, both now applied in session 3d. The reasoning is kept because
it is the answer to "why doesn't your model use location?" at the pitch.

### Q8 — Calendar

**Settled:**

- Public-sector salary dates: **days 25–30**, kept as a labelled assumption.
  It drives the largest recurring spike in the generated data.
- Evening peak: **19:00–22:00**, kept as a labelled assumption. The
  06:00–11:00 *trough* is confirmed by the عروض الصبح time condition.
- **Ramadan seasonality: removed.** Agreed — it needs real per-year dates, the
  window shifts ~11 days annually, and the effect we would have applied was a
  large guess. A large guessed effect is worse than none: it puts structure in
  the data that the models will learn and that nothing validates.

**Weekend days: KEPT, minimally.** ✅ Applied.

This is not the same kind of assumption as Ramadan, for three reasons:

1. **It is not really a guess.** Libya's official weekend being Friday–Saturday
   is a public fact about the country, not an operator business number we are
   estimating. There is nothing to be wrong about.
2. **It costs almost nothing.** One boolean derived from the date. No overlay,
   no multiplier to invent, no per-year maintenance.
3. **It earns its place in the feature set.** `weekend_usage_share_30d` is one
   of the few cheap signals of whether a subscriber's mornings are actually
   free — and generated data with no weekly rhythm at all would make that
   feature constant, which is a data-generation choice quietly deciding a
   modelling result.

There is also a product reason: a 06:00–11:00 morning pass almost certainly
sells differently on a work morning than on a Friday. If `offpeak_data_ratio`
has no weekday structure, M3 cannot tell a commuter from someone who sleeps in.

**As applied:** `weekend_days: [friday, saturday]` is `confirmed`, with
`apply_usage_multiplier: false`. There is an `is_weekend` feature family and
`sequences.require_weekly_periodicity: true`. No usage multiplier anywhere —
the weekly rhythm comes from the flag alone.

### Q9 — Geography and network quality

**DECIDED: geography layer removed, network-quality feature kept.** ✅ Applied.
These are two things bundled under one heading and they deserve different
answers.

**Remove geography — agreed, and for a stronger reason than "no data".**

With M5 gone, geography has almost no consumer left:

- The Network Risk Map screen is gone.
- `district` survived only so the fairness guardrail could *forbid* it, which
  is circular: generating a field purely so a test can assert we did not use it.
- It costs a dataset (OpenCelliD), an API key, and a CC BY-SA attribution
  obligation on every slide that shows it.
- Per-cell off-peak trough detection loses its basis — but that is fine,
  because we now have the operator's *actual* window. Falling back to the
  national 06:00–11:00 band is not a compromise, it is using the real answer.

**But keep network quality as a plain subscriber-level feature.**

`dropped_call_rate_30d` is not an invented Libyan field. It comes from the real
datasets:

- UCI Iranian has a **`Call Failures`** column — one of the four reasons that
  dataset was chosen as the anchor in the first place.
- Cell2Cell has `dropvce`, `blckvce`, `unansvce`.

So this is real signal from real data, mapped through. Dropping it would throw
away measured churn predictors to simplify something that is already simple.
The change is to make it **subscriber-level rather than cell-level**: no cell
join, no hourly load matrices, no geography — just "how bad is this
subscriber's service".

That still keeps the Component 2 seam alive at zero cost. If your teammate's
Network ML lands, they supply a better version of the same subscriber-level
number and nothing in M1 changes.

**The fairness consequence, as applied.** Without `district` the redlining
audit had nothing to audit, so `audit_redlining` was replaced by
`audit_distribution(mean_by_group, dimension)` across **value deciles and
tenure bands**. It asks a real question — are we systematically giving less to
low-value or newer subscribers? — and a gap is *expected*, because loyalty
tiers exist and `d_max` rises with tenure by design. What it catches is a gap
wider than the published ladder explains.

`district` stays on `forbidden_pricing_features` even though nothing generates
it, so that reintroducing geography later cannot silently make it a price
lever. A test asserts that.

---

## What to do next

Nothing blocks the synthesis engine. Remaining work is the two decisions above,
then building Layer 1.

Small gap still worth confirming when convenient: **Q6b**, partial-recharge
behaviour on an outstanding emergency-credit debt. It affects the M4 label
definition.

## Recording answers

When you replace a value:

1. Change the block's `status:` from `assumption` to `confirmed`.
2. Add a `source:` line saying where it came from.
3. Update the counts at the top of this file.
