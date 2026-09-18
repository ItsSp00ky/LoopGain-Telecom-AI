# Integration Contract

**How the other platform components talk to CVM (`ali_branch`).**

Audience: whoever owns Component 4 (Customer Chatbot) or Component 5 (Employee
Telecom Copilot), and whoever owns Component 2 (Network ML).

The short version: **CVM is an HTTP service.** You call it, you do not import
it. If you find yourself writing `from cvm...` or opening our DuckDB file, stop
— something is wrong with the seam.

---

## 1. Why HTTP and not a shared library

Four reasons, and they are worth understanding before you argue for a shortcut:

- **The feature store will change.** DuckDB is correct at demo scale; at 6M+
  subscribers it becomes Spark or a columnar warehouse. If you query the file,
  your component breaks on that day. If you call the API, it does not.
- **Guardrails must not be bypassable.** Every price and every credit limit
  passes six constraints before it leaves the decision engine. An importer can
  call the pricing function directly and skip them. An HTTP caller cannot.
- **The audit log.** Every decision persists its inputs, weights, active
  constraints and reason codes. Decisions made through the API are logged;
  decisions made by importing a function are not, and "why did this subscriber
  get this offer?" becomes unanswerable.
- **We can deploy independently.** Your agent and our models ship on different
  days without coordinating a merge.

---

## 2. Base URL and health

| Environment | Base URL |
|---|---|
| Local (both on one laptop) | `http://localhost:8000` |
| Docker Compose, same network | `http://api:8000` |
| Demo host (Oracle Free Tier) | set at deploy time |

Always check readiness before your first call:

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "degraded",
  "version": "0.1.0",
  "env": "dev",
  "models_loaded": {
    "m1_churn_lightgbm": true,
    "m1b_survival": true,
    "m2_clv": true,
    "m4_repayment_pd": true
  },
  "feature_store_reachable": true
}
```

`status` is `ok` only when **every** model is loaded and the store is readable.
`degraded` means some endpoints will return **503** — check `models_loaded`
rather than retrying blindly. A partial deploy is visible on purpose; an API
reporting `ok` with no models loaded would be worse than one reporting nothing.

Interactive docs, always current: **`http://localhost:8000/docs`**.
The OpenAPI spec is at `/openapi.json` — generate a typed client from it rather
than hand-writing request models.

---

## 3. The contract

Six endpoints. These are frozen; anything not listed here is internal and may
change without notice.

| Endpoint | Method | Purpose |
|---|---|---|
| `/v1/cohort/query` | POST | Filter a population → hashed IDs + aggregate |
| `/v1/score/churn` | POST | Calibrated churn probability, optional time-to-churn |
| `/v1/subscriber/{id}` | GET | Full 360 view for one subscriber |
| `/v1/offer/next-best` | POST | Recommended offer, priced and guardrailed |
| `/v1/price/quote` | POST | Price one specific bundle |
| `/v1/advance/limit` | POST | Learned airtime advance limit |

**Not here, and not coming from us:** network anomaly detection (Component 2)
and care-text classification (Component 4). CVM consumes per-cell quality
signals as churn features; it does not produce them, and it does not read
complaint text.

### Two rules that apply to every call

**Identifiers are salted SHA-256 hashes.** 64 lowercase hex characters. There is
no endpoint that accepts a raw MSISDN, and sending one gets a `422`, not a
score. If your component holds raw numbers, hash them with the same salt
(`CVM_HASH_SALT`) before calling — the salt must match ours or the IDs will not
resolve.

**Everything is read-only.** No endpoint creates, alters or approves anything.
`/v1/offer/next-best` *computes* an offer; it does not send it. Delivery is the
Campaign Builder's job.

### One contract change since the freeze

`/v1/score/churn` previously accepted an optional `arm` field selecting an M1
benchmark arm, and `/v1/subscriber/{id}` returned an `lstm_churn_probability`
beside the main score. **Both are gone.** M1 is a single gradient-boosting
model family now, so the knob selected between one option, and the second
probability did not exist to return.

`extra="forbid"` is set on every request model, so a caller still sending `arm`
gets a **422 with the field named** rather than silent acceptance. Nothing else
in the six endpoints changed.

---

## 4. Worked example — the Copilot's flagship question

> *"Which Benghazi subscribers are at risk because of coverage, and what should
> we offer them?"*

Your agent decomposes this into three calls. It does not write SQL.

**Step 1 — resolve the cohort.**

```http
POST /v1/cohort/query
Content-Type: application/json

{
  "district": "Benghazi",
  "min_dropped_call_rate": 0.04,
  "min_churn_probability": 0.5,
  "limit": 200
}
```

```json
{
  "subscriber_ids": ["3f2a...e91c", "8b17...02da"],
  "total_matched": 1843,
  "returned": 200,
  "total_revenue_at_risk_lyd": 264192.0,
  "filter_applied": { "district": "Benghazi", "...": "..." }
}
```

`total_revenue_at_risk_lyd` is churn probability × predicted CLV summed over
the matched cohort — a CVM number, not a network one.

**Step 2 — score them.**

```http
POST /v1/score/churn
{ "subscriber_ids": ["3f2a...e91c"], "include_survival": true }
```

Returns a calibrated `churn_probability`, a `decile`, `time_to_churn_days`, and
`top_drivers` — SHAP contributions already rendered in plain language
("has not topped up in 23 days"). **Use the `plain_language` field in your
answer.** Do not paraphrase the raw feature names; the wording has been checked.

**Step 3 — get the recommendation.**

```http
POST /v1/offer/next-best
{ "subscriber_id": "3f2a...e91c", "channel": "api" }
```

```json
{
  "offer_id": "OFF-2026-0417-0093",
  "price_lyd": 8.5,
  "base_price_lyd": 10.0,
  "discount_pct": 0.15,
  "bonus_mb": 2048,
  "valid_from_hour": 2,
  "valid_to_hour": 6,
  "tier": "gold",
  "instrument": "offpeak_data",
  "reason_codes": ["loyalty_reward", "coverage_degradation", "offpeak_capacity"],
  "customer_facing_reason_en": "Loyalty reward - 6 years with us",
  "expected_margin_lyd": 4.2,
  "constraints": [
    { "name": "margin_floor", "binding": false, "detail": "..." },
    { "name": "clv_ceiling",  "binding": true,  "detail": "..." }
  ],
  "decision_log_id": "DL-8f21c4"
}
```

**Cite `constraints` and `reason_codes` in your answer.** That is how you
explain *why* an offer was chosen without inventing a reason. The one with
`"binding": true` is the constraint that actually set the number — in this
example the offer was capped by the CLV ceiling, not by the discount formula.

---

## 5. Grounding rules for LLM-based components

These are not suggestions. They are project commitments (proposal §6.5), and
they are the answer to the evaluator question *"why isn't the LLM making the
pricing decisions?"*

1. **The LLM never sets a price, a bonus or a credit limit.** It reads the
   numbers this API returns and explains them. An LLM has no place in a path
   that moves money.
2. **Never invent a number.** If the API did not return it, it does not go in
   the answer. A plausible-sounding fabricated LYD figure in a live demo is the
   worst possible failure.
3. **Cite the tool output.** Every claim traces to a response field. Show the
   tool-call trace in your UI — evaluators need to see grounding, not trust it.
4. **Refuse rather than guess.** If no call produced supporting output, say so.
   "I could not determine that" beats a confident wrong answer.
5. **Never expose a raw identifier**, even if you hold one. Hashes only.
6. **Do not cache decisions.** Prices and limits are recomputed against current
   guardrails and budget; a cached offer may violate a constraint that has since
   bound.

### For RAG

The following are stable and safe to index. They are written to be read by both
humans and retrievers, which is why they explain reasoning rather than just
describing behaviour:

```
docs/model_cards/        one per model: intended use, metrics, limitations, ethics
docs/data_dictionary.md  every field, its source and its generation logic
docs/architecture.md     the layer map and the temporal framing
docs/adr/                why non-obvious decisions were made
conf/pricing.yaml        the six guardrails, with their thresholds
conf/advance.yaml        the credit safety guards
```

Re-index whenever a model card or guardrail config changes, or the agent will
cite a rule the system no longer applies — worse than not answering, because it
looks authoritative.

---

## 6. What we need *from* Component 2 (Network ML)

This is the one place CVM is a consumer rather than a provider.

Network quality drives churn in Libya — power instability, fuel supply and
fibre cuts produce localised degradation, and subscribers on bad cells leave.
So M1 wants per-cell quality signals as ordinary features. **We do not model
the network.** That is Component 2's job, and duplicating it would mean two
teams maintaining two answers to the same question.

What CVM needs, keyed by `cell_id`, refreshed daily:

| Field | Type | Meaning |
|---|---|---|
| `cell_id` | str | Matches the OpenCelliD MCC-606 identifier |
| `dropped_call_rate_30d` | float | 0–1 |
| `data_session_failure_rate` | float | 0–1 |
| `cell_outage_hours_30d` | float | Hours down in the last 30 days |
| `hourly_load_curve` | float[24] | Mean utilisation by hour — **we need this for off-peak trough detection** |
| `is_anomalous` | bool | Optional. If Component 2 has an anomaly model, we will use its flag as a feature rather than building our own. |

Configure the source in `conf/features.yaml`:

```yaml
network_quality:
  source: generated          # generated | external
  external_endpoint: http://network-ml:8100/v1/cells/quality
```

Until Component 2 is ready, the synthesis engine generates these fields so M1
can be trained and the pipeline exercised end to end. Swapping to `external`
does not change M1 — the feature names are identical by design, which is the
whole reason for agreeing them now rather than at integration week.

**The `hourly_load_curve` is the one to nail down early.** M3's per-cell
off-peak trough detection depends on it, and it is the only field here that a
network-monitoring system might not already expose in the shape we need.

---

## 7. Starter kit for the Copilot owner

Working scaffolding — module docstrings, tool structure, the read-only
constraints already encoded — is in
[`docs/integration/copilot_starter/`](integration/copilot_starter/).

It was written as part of this repo's original scope and then handed over. It
is a starting point, not a dependency: copy it into your own repository, do not
import it from here.

---

## 8. Reporting a problem with this contract

Open an issue on this repo with the `integration` label. Include the endpoint,
the request body, the response you got and the one you expected.

If you need a **new** field or endpoint, raise it before building around the
gap. Adding a field is usually easy; discovering after integration week that
two components assumed different semantics for the same number is not.
