# Market questions — Almadar Aljadid

Status board for the domain facts the synthesis engine needs. Answers live in
[`conf/market.yaml`](../conf/market.yaml) and
[`conf/catalogue.yaml`](../conf/catalogue.yaml).

**Operator: Almadar Aljadid (المدار الجديد), MCC/MNC 606-01.** Libyana is
modelled only as the competitor that dual-SIM leakage flows toward.

| | Answered | Still open |
|---|---|---|
| Count | 4 | 6 |

---

## ✅ Answered

### Q1 — Recharge denominations · **confirmed**

**3 / 5 / 10 / 20 / 40 / 100 LYD.**

In `conf/market.yaml#recharge`. Two consequences worth knowing:

- The **3 LYD floor** is load-bearing for M4. The نت في وقته data advance costs
  5 LYD, so a subscriber who habitually buys the smallest card *cannot clear
  that debt in one top-up*. That is the structural finding the whole M4
  argument now rests on.
- The cheapest data bundle is **0.5 LYD** (نت 50MB), so monetary fields must
  not be rounded to whole dinars anywhere in the pipeline.

*Still an assumption:* the **popularity split** across those six values. The
ladder is confirmed; the weighting is our guess. Any recharge agent could
answer this in thirty seconds — worth asking.

### Q3 — Bundle catalogue · **confirmed**

**57 bundles across 17 families**, from `Almadar/internet_offers_data_v4.csv`,
now structured in [`conf/catalogue.yaml`](../conf/catalogue.yaml).

Families: Mix (five quality tiers × four durations), Golden and Silver
unlimited, daily / weekly / monthly data, 5G monthly and hourly, Macchiato
hourly unlimited, Social, Elite, Family share, and the morning off-peak pass.

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

---

## ❔ Still open

Ordered by how much they matter.

### Q2 — Pay-as-you-go tariffs ⭐ highest priority now

The catalogue covers bundles. It says nothing about what a subscriber pays with
**no bundle active** — which is the baseline every bundle is a discount
against, and what makes `bundle_vs_payg_share` meaningful.

- On-net call (Almadar → Almadar), per minute
- Off-net call (Almadar → Libyana), per minute
- International, per minute
- SMS, on-net and off-net
- Data, per MB
- Is voice billed **per second or per minute**?

Current values in `conf/market.yaml#payg` are guesses.

### Q3b — Bundle volumes and costs

Two gaps inside the otherwise-confirmed catalogue:

**Volumes.** Most CSV rows left the Data column blank, so volumes were inferred
from package names — `نت 6` → 6 GB, `نت 1/2` → 512 MB, and so on. Worth a
spot-check on a few. Two rows I could not resolve at all: `نت ساعة 1_5G` and
`نت ساعتين 2_5G` — is that unlimited within the hour, or a volume cap?

**Costs.** `variable_cost_lyd` on all 57 bundles is an **estimate** — 25% of
price for metered data, 35% for unlimited. Nobody outside the operator knows
the real marginal cost of a gigabyte, but the margin-floor guardrail needs
*something* to enforce. Keeping the estimate is fine; **saying it is an
estimate in the report is not optional**, because otherwise a stated margin
looks audited when it is not.

### Q5 — Zero-rated apps

There is a real Social family (1 / 5 / 20 LYD), so `social_bundle_share` is a
live feature. Remaining question: are any apps **zero-rated** — traffic that
does not consume the data allowance at all? That changes how data usage should
be generated for social-heavy subscribers.

### Q7 — Base and economics

Still carrying the proposal's own estimates:

| | Assumed |
|---|---|
| Addressable prepaid subscribers | 1,000,000 |
| Monthly ARPU | 12 LYD |
| Monthly silent churn | 3.5% |
| Dual-SIM penetration | 60% |

An LPTIC annual report, a regulator publication or a press figure would be
better. If nothing exists, keep these and label them illustrative — the
business case is explicitly a method demonstration, not a forecast, and
estimates are fine **when labelled**.

One sanity check worth doing: 12 LYD monthly ARPU against this catalogue looks
low. The cheapest monthly data bundle is 20 LYD and the Mix tiers start at
20–35 LYD for a month. Either ARPU is higher than assumed, or most subscribers
live on daily and weekly bundles rather than monthly ones. **Either answer is
interesting and should be resolved**, because it changes the whole CLV
distribution.

### Q8 — Calendar

- **Public-sector salary dates.** Assumed days 25–30. This drives the largest
  recurring spike in the generated data.
- **Ramadan dates** for the modelling window — needs real calendar dates.
- **Peak hours.** The 06:00–11:00 trough is confirmed; the evening peak
  (assumed 19:00–22:00) is not.
- **Weekend days.** Assumed Friday and Saturday.

### Q9 — Geography

- Is the district list and its population weighting roughly right?
- Where is service actually worst? Assumed the south (Sabha, Ubari, Ghat) and
  peri-urban areas, driven by power and fuel supply. This feeds the
  network-quality features that M1 consumes.

### Q10 — Language

- Rough split across MSA, Libyan dialect, Amazigh and English.
- Should the channel simulator default to **MSA or dialect**? Dialect reads as
  more authentic; MSA is safer if the evaluators are not Libyan.

---

## What to do next

**Q2 is the blocker.** Everything else has either a confirmed value or a
defensible labelled estimate. Pay-as-you-go tariffs are the one remaining gap
that makes a *feature* meaningless rather than merely approximate.

After that, in order: Q3b volumes (quick spot-check), Q7 the ARPU-versus-
catalogue mismatch, then the rest.

## Recording answers

When you replace a value:

1. Change the block's `status:` from `assumption` to `confirmed`.
2. Add a `source:` line saying where it came from.
3. Update the count at the top of this file.

A number without recorded provenance will get asked about, and "it was in the
config" is not an answer.
