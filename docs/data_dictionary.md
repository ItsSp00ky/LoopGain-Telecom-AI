# Data Dictionary

**Deliverable D11.** Every field: type, source (real vs generated), and
generation logic.

Owner: **E1.** Adding a generated field without an entry here gets the PR
rejected — see [CONTRIBUTING.md](../CONTRIBUTING.md).

The `Status` column tracks implementation: `planned` → `generated` →
`validated` (passes its Pandera contract and the SDMetrics gate).

**Source** legend:
`real` = comes from a public dataset unchanged ·
`mapped` = a real field rescaled to Libyan units ·
`gen` = produced by CTGAN ·
`overlay` = produced by a business rule on top of the GAN output ·
`derived` = computed in Layer 3 from the above.

---

## Identity & context

| Field | Type | Source | Logic | Status |
|---|---|---|---|---|
| `subscriber_id_hashed` | str(64) | derived | SHA-256 + salt. **No raw MSISDN exists anywhere in this repository.** | planned |
| `snapshot_date` | date | derived | Partition key. Features must end strictly before the label window. | planned |
| `tenure_months` | int | real | From UCI `Subscription Length`. Loyalty backbone. | planned |
| `consecutive_active_months` | int | gen | Conditioned on tenure and recharge regularity. | planned |
| `language_pref` | enum | gen | {ar, ar-LY, ber, en}. Drives message rendering. **Never a pricing input.** | planned |
| `summer_outage_index` | float | overlay | Seasonal outage exposure. | planned |
| `salary_week_flag` | bool | overlay | Public-sector disbursement drives a pronounced recharge spike. | planned |
| `diaspora_roaming_flag` | bool | overlay | Roaming marks a high-value, low-churn segment. | planned |

## Monetary & recharge dynamics

| Field | Type | Source | Logic | Status |
|---|---|---|---|---|
| `recharge_amount_lyd` | float | mapped | Multinomial over the **confirmed** Almadar ladder {3, 5, 10, 20, 40, 100} LYD, weighted low, conditioned on value percentile. | planned |
| `modal_recharge_amount_lyd` | float | derived | The subscriber's most common top-up. **Basis of the M4 affordability ceiling** — the mean is dragged up by one salary-week top-up they will not repeat. | planned |
| `recharge_channel` | enum | gen | {scratch_card, agent_erecharge, almadar_app, bank_card, p2p_transfer}, weighted to scratch/agent given low banking penetration. | planned |
| `recharge_count_30d` | int | gen | Poisson, λ from mapped spend percentile. | planned |
| `recharge_count_90d` | int | gen | As above. | planned |
| `days_since_last_topup` | int | gen | Inter-arrival sampling. **The strongest single churn signal in prepaid.** | planned |
| `mean_inter_recharge_days` | float | derived | Mean gap over 90d. | planned |
| `recharge_gap_cv` | float | derived | Coefficient of variation of gaps. **Irregularity precedes exit.** | planned |
| `balance_zero_hours_30d` | float | gen | Hours at zero balance. **No postpaid equivalent exists.** | planned |
| `failed_bundle_attempts_30d` | int | gen | Purchases rejected for insufficient balance. Pure affordability signal. | planned |
| `credit_transfer_out_lyd` | float | gen | Peer-to-peer credit sharing. | planned |

## Emergency credit dynamics (M4)

Almadar runs **two** emergency-credit products, both confirmed from operator
documentation ([`conf/catalogue.yaml`](../conf/catalogue.yaml#emergency_credit)):

- **رصيد في وقته** — airtime advance, 1/3/5 LYD, `*140#`, gate: balance ≤ 0.5 LYD
- **نت في وقته** — emergency data, flat 5 LYD / 2 GB / 3 days, `*000#`,
  gate: balance ≤ 1 LYD **and** remaining quota < 250 MB

They are mutually exclusive, and neither has a published grace period —
recovery happens at the next recharge or balance transfer in.

| Field | Type | Source | Logic | Status |
|---|---|---|---|---|
| `airtime_advance_count_90d` | int | overlay | Uses of رصيد في وقته. | planned |
| `airtime_advance_amount_lyd` | float | overlay | Must be one of {1, 3, 5} — the operator's real denominations. | planned |
| `data_advance_count_90d` | int | overlay | Uses of نت في وقته. Always 5 LYD; there is no tiering. | planned |
| `advance_settled_by_next_recharge` | bool | overlay | **Supervised label for M4.** Behavioural, not contractual — no grace period is published. | planned |
| `days_to_settle` | int | overlay | Settlement lag, censored at 14. | planned |
| `unpaid_advance_days` | int | overlay | Days carrying unpaid debt. Debt blocks re-subscription, so this measures lockout. | planned |
| `emergency_service_alternations_90d` | int | overlay | Switches between the two products. **Sustained distress signal the incumbent design cannot see.** | planned |
| `advance_exceeded_modal_recharge_flag` | bool | derived | True when the debt was larger than one typical top-up. **The 3-LYD-card / 5-LYD-debt trap, made measurable.** | planned |
| `balance_at_advance_lyd` | float | overlay | Should always be ≤ 0.5 (airtime) or ≤ 1.0 (data) — the eligibility gate, which is why the population is selected on being broke. | planned |

> **Do not generate `entered_recharge_stage_flag` or `line_reset_flag`.** Those
> were Libyana mechanisms. Neither is documented for Almadar, and inventing
> them would mean fabricating the project's headline finding. The honest
> equivalent is service **lockout** — unpaid debt blocking re-subscription.

## Usage & leakage dynamics

| Field | Type | Source | Logic | Status |
|---|---|---|---|---|
| `data_mb_peak` | float | gen | | planned |
| `data_mb_offpeak` | float | gen | Usage inside the 06:00–11:00 عروض الصبح window. | planned |
| `offpeak_data_ratio` | float | derived | Share of data used in the 06:00–11:00 window. Identifies who would actually use a عروض الصبح morning pass. | planned |
| `voice_min_onnet` | float | gen | Billed as a 3-minute block at 0.090 LYD then 0.050/min, **not** a flat rate — so call *length* drives revenue per minute, and the generator must produce a realistic length distribution. | planned |
| `voice_min_offnet` | float | gen | Flat 0.090 LYD/min to Libyana. | planned |
| `voice_min_landline` | float | gen | Flat 0.040 LYD/min — the cheapest voice destination. | planned |
| `payg_data_mb_30d` | float | gen | Data bought at the Bjawak PAYG rate (0.025 LYD/MB) rather than inside a bundle. | planned |
| `payg_data_spend_lyd_30d` | float | derived | **~25× the bundle rate per GB.** High values mean the subscriber is either unaware of bundles or cannot afford one up front. | planned |
| `onnet_ratio` | float | derived | **Dual-SIM leakage proxy.** Falling on-net share means the social graph is migrating. | planned |
| `incoming_outgoing_ratio` | float | derived | **Primary leakage detector.** Rising incoming against flat outgoing = "this is my receiving SIM". | planned |
| `distinct_called_numbers_trend` | float | derived | Contraction of the calling graph precedes silent exit. | planned |
| `ussd_price_check_sessions_30d` | int | gen | Repeated catalogue browsing indicates active price shopping. | planned |
| `social_bundle_share` | float | derived | Share of data spend on the real Social family (1 / 5 / 20 LYD). No apps are zero-rated, so all traffic consumes allowance. | planned |
| `bundle_vs_payg_share` | float | derived | Share of data spend inside a bundle versus at the PAYG rate. | planned |

## Network quality (subscriber-level)

No cells, no coordinates, no districts — geography is out of scope, and all
subscribers are modelled as geographically equivalent. These are **real
measured features**, not invented Libyan ones: UCI Iranian has a
`Call Failures` column and Cell2Cell has `dropvce` / `blckvce` / `unansvce`.

Component 2 (Network ML) can supply better values for the same field names
later; nothing in M1 changes when it does. See
[INTEGRATION.md §6](INTEGRATION.md).

| Field | Type | Source | Logic | Status |
|---|---|---|---|---|
| `dropped_call_rate_30d` | float | mapped | Seeded from UCI `Call Failures` and Cell2Cell `dropvce`. | planned |
| `data_session_failure_rate` | float | gen | Correlated with dropped-call rate. | planned |
| `service_outage_hours_30d` | float | overlay | Power- and fuel-driven downtime this subscriber experienced. One distribution, no geographic variation. | planned |

## Care contact

Volume only. This branch does not read complaint **text** — that is
Component 4's domain. A subscriber who calls support three times in a month is
a churn signal regardless of what they said.

| Field | Type | Source | Logic | Status |
|---|---|---|---|---|
| `care_contacts_30d` | int | gen | Support contacts in 30 days. Seeded from Cell2Cell's care-call counts. | planned |
| `care_contacts_trend` | float | derived | 30d vs prior 60d. A rising trend precedes exit. | planned |

---

## Derived feature families (Layer 3)

Computed in [`src/cvm/features/`](../src/cvm/features). Full definitions in
`conf/features.yaml`.

| Family | Representative features | Module |
|---|---|---|
| Velocity / decay | `revenue_decay_ratio = mean_7d / mean_30d`, plus data/voice/SMS equivalents. Values well below 1.0 are the earliest reliable tell. | `velocity.py` |
| Volatility | Std-dev and CV of inter-recharge gaps; rolling variance of daily data usage. | `velocity.py` |
| Ratios & mix | `onnet_ratio`, `offpeak_data_ratio`, `bundle_vs_payg_share`, `data_to_voice_ratio`. | `velocity.py` |
| Distress | `balance_zero_hours`, `failed_bundle_attempts`, downgrades, consecutive sub-5-LYD recharges. | `distress.py` |
| Leakage | `incoming_outgoing_ratio` trend, off-net share trend, distinct-called-numbers contraction. | `wallet_leakage.py` |
| Credit | Advance frequency per product, settlement lag, unpaid days, alternation between the two emergency services, modal recharge. | `distress.py` |
| Network quality | Outage-hours-weighted dropped-call rate over home cell and top-3 visited cells. Consumed as plain M1 features — no network model here. | `velocity.py` |
| Sequence tensors | Per-subscriber 90 × k daily matrices. **Direct input to the M1 LSTM — no aggregation applied.** | `sequences.py` |

## RFM-LE

Textbook RFM assumes purchase transactions. Prepaid has none, so each dimension
is redefined and two are added.

| Dim | Standard | Our prepaid definition |
|---|---|---|
| **R** Recency | Days since last purchase | Days since last **revenue-generating event**. Usage alone does not count — a subscriber burning residual credit generates no revenue. |
| **F** Frequency | Transaction count | Recharge count in 90d, **penalised by `recharge_gap_cv`**. Five regular recharges beat five erratic ones. |
| **M** Monetary | Total spend | Total LYD in 90d, **plus the 30d-vs-prior-60d slope**, so decline is visible inside the score itself. |
| **L** Loyalty | *(added)* | `0.4·tenure_scaled + 0.3·consecutive_active_months_scaled + 0.3·lifetime_recharge_percentile` |
| **E** Engagement | *(added)* | Service breadth across {voice, SMS, data, bundles, transfers, advances}, normalised. |

Quintile scoring 1–5 per dimension gives an `R|F|M|L|E` cell, collapsed into
eight segments: Champions, Loyal High-Value, Potential Loyalists, Promising
New, Needs Attention, At-Risk Valuable, Hibernating, Lost.

---

## Excluded from the feature matrix

Enforced by `conf/features.yaml#leakage_controls.excluded_columns` and
`tests/leakage/test_point_in_time.py`.

| Field | Why excluded |
|---|---|
| `Customer Value` (UCI) | Pre-computed; partially encodes the outcome. Dropping it is why our metrics are lower than the published ~0.99 AUC. |
| `hazard_score` | Our own label generator. |
| `churn_date` | The label, restated. |
| `snapshot_date` | Partition key; would let a model learn the split. |
| Everything in `hazard.LABEL_GENERATING_FIELDS` | Any field the synthetic label was drawn from. |
