# Integration guide for the team platform

How the other components of the Loop Gain platform use this module (ticket T20, decisions 10 and 17).

Audience: whoever owns the customer chatbot, the employee copilot, the network ML module and the antenna and cell placement module.
Adapted from `Ali_Branch`'s `docs/INTEGRATION.md`, which was written for its own API.

The short version: this module is an HTTP service.
You call it, you do not import it.
If you are writing `from prepaid_churn...` or opening one of our CSV files, stop: the seam is in the wrong place.

## 1. Why a service and not a shared package

- The guardrails have to be unavoidable.
  A retention offer reaches a customer only after a named person approved it (decision 14), and the service serves only approved rows.
  Someone importing `retention.propose` gets proposals that nobody reviewed, and the approval step quietly disappears.
- What the chatbot may see and what the copilot may see are different.
  Two keys on two sets of endpoints enforce that in one place.
  Inside a shared package every consumer can read everything.
- The files move.
  Today the outputs are CSV and JSON under `artifacts/`; at operator scale they are a warehouse.
  A component that reads our files breaks that day, and a component that calls the service does not.
- We deploy on different days than you do.

## 2. Starting it, and the base URL

Both keys are required and have no default, so whoever deploys the service sets them:

```bash
export PREPAID_CHURN_CHATBOT_KEY="<a long random string>"
export PREPAID_CHURN_COPILOT_KEY="<a different long random string>"
uv run churn serve
```

On Windows PowerShell, use `$env:PREPAID_CHURN_CHATBOT_KEY = "..."` instead of `export`.
Use two different random keys of at least 24 printable ASCII characters, without spaces.

| Where | Base URL |
|---|---|
| Both components on one laptop | `http://127.0.0.1:8000` |
| A teammate's laptop on the same network | `http://<the serving laptop's IP>:8000`, with the service started as below |
| A demo host | set at deploy time, and tell the other owners |

To be called from another laptop, start the service with `uv run churn serve --host 0.0.0.0`, so that it listens on the laptop's network address and not only on itself.
`ipconfig` on Windows or `ip addr` on Linux shows that address.
Do this only on a network you trust, for as long as the call takes: the keys still apply, but the service is not built to face the internet (T15).
Windows may ask whether to let Python through its firewall.

Ask for readiness before your first call, and read the answer rather than retrying blindly.
Every example in this guide was captured on 2026-09-27 from the real service, holding the 30,000-subscriber base and a copy of the demo campaign in which subscriber 70008's offer was approved:

```json
{
  "status": "ok",
  "bundle_loaded": true,
  "smoke_prediction_passed": true,
  "model_version": "lightgbm-2026-09-19-ef9430fb",
  "problems": [],
  "latest_outputs": {
    "loaded_at": "2026-09-27T03:23:10+00:00",
    "scored_at": "2026-09-26T15:28:25+00:00",
    "campaign_id": "9dba975e547218ac0b11b593dee169b95a45e3a345438de12f53ea99771286de",
    "campaign_created_at": "2026-09-26T16:26:03+00:00",
    "subscribers_in_portfolio": 30000,
    "approved_offers": 1
  }
}
```

`status` is `ok` only when the bundle predicts and there is a portfolio to summarise.
`degraded` means an output is missing or invalid, or approved offers have been withheld after leaving the current catalogue; `problems` explains why.
An endpoint needing a missing output answers 503; a withheld offer answers 404, like any other unavailable offer.
The campaign is read again whenever a reviewer approves an offer, so a new approval is served on your next request without a restart, and `approved_offers` goes up when it lands.
`campaign_id` tells you which campaign you are looking at.
The model and the scored portfolio are read at startup, so a new model or scoring run is served after a restart.

The OpenAPI page at `/docs` is generated from the response models, so it is always the current field list.
Generate your client from `/openapi.json` rather than hand-writing request models.

## 3. The endpoints

| Endpoint | Key | What it answers |
|---|---|---|
| `GET /health` | none | Whether the bundle predicts, and which outputs are being served |
| `GET /catalogue` | chatbot | Every operator package on sale, with its collection date |
| `GET /subscribers/{id}/retention` | chatbot | The approved offer for one subscriber and the message to say, or 404 |
| `GET /portfolio/summary` | copilot | Customers and LYD at risk by risk band and value tier, with the model's test results |
| `GET /subscribers/{id}/risk` | copilot | One subscriber's risk, the model's reasons, and their value tier |

Send your key in the `X-API-Key` header.
Each key is accepted only on its own endpoints: the chatbot key on `/portfolio/summary` is 403, and the copilot key on `/catalogue` is 403.
That is deliberate, so a leaked chatbot key cannot read the portfolio.

Two rules apply to every call.

**Identifiers are pseudonymous.**
An ID shaped like a Libyan mobile number is refused with 422 rather than looked up.
If you hold raw numbers, hash them first; `prepaid_churn.privacy.pseudonymize` is the supported way, and the operator's export should already have done it.

**Everything is read-only.**
Every route is a GET, and a test asserts that the generated OpenAPI document contains no other method.
Nothing can be created, changed or approved through this service, and no offer appears until a named reviewer approved it with `churn approve`.

## 4. A chatbot turn

The customer asks what they can get today.
Two calls, and nothing invented between them.

`GET /catalogue` returns all 37 packages; one row:

```json
{
  "offer_id": "HR5G_1",
  "operator": "Libyan mobile operator",
  "family_ar": "باقات الساعة",
  "family_en": "Hourly 5G",
  "name_ar": "نت ساعة 1_5G",
  "name_en": "Net 1 hour 5G",
  "price_lyd": 5.0,
  "validity_ar": "ساعة",
  "validity_hours": 1.0,
  "data_gb": null,
  "data_unlimited": true,
  "voice_minutes": null,
  "voice_unlimited": false,
  "network": "5G",
  "valid_from_hour": null,
  "valid_to_hour": null,
  "collected": "2026-09-18"
}
```

`data_gb` is null when the package states no volume; `data_unlimited` says which of the two it is.
`collected` is when that row was read from the operator's material, because prices change and a stale price quoted to a customer is a complaint.

`GET /subscribers/70008/retention` returns the approved offer:

```json
{
  "subscriber_id": "70008",
  "recommended_offer_id": "DAY_50MB",
  "customer_message_ar": "هديتك: نت 50MB لمدة يوم.",
  "customer_message_en": "Your gift: Net 50MB for a day.",
  "offer_reason_en": "Catalogue bonus: Net 50MB; positive value under the stated retention assumptions.",
  "offer_reason_ar": "مكافأة من الكتالوج: نت 50MB؛ قيمة موجبة وفق افتراضات الاحتفاظ.",
  "reviewed_at": "2026-09-27T03:23:02+00:00",
  "campaign_id": "9dba975e54...",
  "offer": { "offer_id": "DAY_50MB", "name_ar": "نت 50MB", "price_lyd": 0.5, "validity_hours": 24.0, "data_gb": 0.05, "...": "..." }
}
```

Say `customer_message_ar` to the customer, or `customer_message_en` in English: it names the package, what it gives when the operator's own material states it, and for how long, and fits one SMS.
Net 50MB's volume is only in its name, so the message does not repeat it; the morning pass's content is stated, so its message says it.
The morning pass's message also gives its hours, `من 06:00 إلى 11:00`.
`offer_reason_*` is why the policy chose the offer, written for staff: never say it to the customer, because it tells them the operator computed their value (decision 51).
Anything more about the package comes from `offer`, and only from it.
There is no churn probability, risk band or value figure in this response, and there never will be: the customer is not told how likely the operator thinks they are to leave.
The offer is a bonus the operator grants, not a discount on a price, so do not quote `price_lyd` as what the customer pays for it.

**404 is a normal answer.**
No campaign, no proposal, a proposal nobody reviewed and a proposal a reviewer rejected all return the same 404 with the same message.
Telling the customer which one it was would tell them an offer was considered and refused.
Say that there is nothing today, and offer nothing else.

## 5. A copilot question

"How much revenue is at risk this month, and is the model still fit for use?"

`GET /portfolio/summary` answers both in one call.
Every LYD figure uses the 70 LYD anchor of decision 42.

```json
{
  "model_version": "lightgbm-2026-09-19-ef9430fb",
  "subscribers": 30000,
  "risk_available": true,
  "by_risk_band": [
    { "name": "high", "customers": 1209, "monthly_spend_lyd": 68449.7, "lyd_at_risk": 37393.2 },
    { "name": "medium", "customers": 3594, "monthly_spend_lyd": 206800.4, "lyd_at_risk": 125861.0 },
    { "name": "low", "customers": 22779, "monthly_spend_lyd": 1626210.3, "lyd_at_risk": 145609.8 },
    { "name": "already_silent", "customers": 2418, "monthly_spend_lyd": 40330.6, "lyd_at_risk": 0.0 }
  ],
  "by_value_tier": [ { "name": "very_high", "customers": 4799, "...": "..." } ],
  "success_thresholds": {
    "capture": { "description": "Share of churners among the riskiest 10% of customers", "value": 0.615, "required": ">= 0.5", "passed": true },
    "...": "..."
  },
  "test_metrics": { "lightgbm": { "roc_auc": 0.891, "pr_auc": 0.348, "...": "..." } },
  "release_gate_passed": true
}
```

What each number means, so the copilot does not describe it as something it is not:

- `monthly_spend_lyd` is assumed monthly recharge at the frozen T18 rate, not observed operator revenue.
- `lyd_at_risk` is each customer's 12-month value scenario weighted by their churn probability, so it is an expected loss under stated assumptions, not money already lost.
  It is null when the export carries no risk estimate, which is what `risk_available: false` means.
- `success_thresholds` are the four checks of decision 13, measured once on the frozen test window, not this month.
- `already_silent` customers are not at risk of churning; they already did.

Cite these field names when the copilot quotes a number, and say the assumption alongside the figure.
[model_card.md](model_card.md) is the long version of the same limits.

### The customer on the phone

"Employee has customer 70008 on the line: what do we know?"

`GET /subscribers/70008/risk`, with the copilot key.

```json
{
  "subscriber_id": "70008",
  "churn_probability": 0.52419242304383,
  "risk_band": "high",
  "reasons": [
    "This month's share of the last two months' total minutes (50% = stable): 0%",
    "Amount recharged on the last recharge day this month: 0",
    "Local incoming minutes this month: 0"
  ],
  "value_tier": "low",
  "value_status": "scenario",
  "value_12m_low_lyd": 10.25,
  "value_12m_base_lyd": 34.24,
  "value_12m_high_lyd": 103.44,
  "monthly_spend_lyd": 37.73,
  "model_version": "lightgbm-2026-09-19-ef9430fb",
  "tier_version": "tiers-v1-efc9739afad4",
  "scored_at": "2026-09-26T15:28:25+00:00"
}
```

`reasons` are the model's own factors, each a short label with the customer's value, in the order the model ranked them.
A `low` subscriber gets one line instead, "Low risk: nothing stands out", and an already silent one gets "No calls and no mobile data this month" (decision 40).
Quote them; do not paraphrase them into a story, and do not add a reason the list does not contain.
They explain the score, not the customer: "no recharge on the last recharge day" is what the model reacted to, not a diagnosis.

This is the copilot's endpoint and only the copilot's.
The same subscriber under the chatbot key is 403, and the chatbot's own offer lookup is 403 for the copilot, although both paths start with `/subscribers/{id}`.
404 here means the subscriber is not in the scored export, which is not the loaded 404 of the offer lookup; nothing is being hidden.

### What it does not answer yet

Found by walking the questions each consumer actually gets (T20), and left out on purpose.
Ask if you need one, rather than working around it:

| Question | Why there is no endpoint |
|---|---|
| "What package am I on, and what do I spend?" (chatbot) | The operator view (T18) exists as a file but is an assumption of this module, not an operator fact. The operator's own systems answer it correctly and in real time. |
| "How much credit can I borrow?" (chatbot) | The T19 advice is a proposal for a person, and no reviewer step exists for it yet. An offer needs an approval (decision 14) and so does a credit limit. |
| "Give me the 200 riskiest customers" (copilot) | A bulk customer-level export over HTTP is what the de-identification rule exists to prevent (decision 17). Analysts read the committed exports or the demo app. |
| "What is waiting for review, and what did we approve this week?" (copilot) | Campaign state is written by `churn decide` and `churn approve` and shown in the demo app. Serving it would put a review queue in a read-only service. |

## 6. Rules for the components that use a language model

These are project commitments (decision 17), and they are the answer to "why is the LLM not making the decision?".

1. **The model never sets an offer, a price or a credit limit.**
   It reads what the service returned and explains it.
2. **Never invent a number.**
   If the response did not carry it, it does not go into the answer.
3. **Cite the field.**
   Every figure in an answer traces to a response field, and the tool call should be visible in your interface.
4. **Refuse rather than guess.**
   "I could not determine that" beats a confident wrong answer, and a 404 or a 503 is a refusal, not an invitation to improvise.
5. **Never show a raw phone number**, even if your component holds one.
   Pseudonymous IDs only.
6. **Do not cache an offer.**
   An approval can be superseded by a new campaign, and a cached offer outlives the review that allowed it.
   Call `/subscribers/{id}/retention` per conversation.
7. **Say the customer message, never the reason.**
   `customer_message_*` is written for the customer; `offer_reason_*` is the policy's reason, for staff (decision 51).

## 7. What the copilot may index

These files are aggregate, stable and written to be read by a retriever as well as a person:

```
docs/model_card.md        intended use, metrics, limitations, ethics
docs/decisions.md         why every non-obvious choice was made
docs/data_contract.md     the input contract
docs/output_contract.md   every column this module writes
docs/operator.md           the catalogue, the market facts and their statuses
docs/integration.md       this file
reports/*.md              the evaluation, tiers, retention, operator view and emergency credit results
```

Do not index anything with one row per customer: `data/raw/`, `artifacts/` and every campaign directory.
They hold subscriber-level data and reviewer names, and a retriever will quote them.
Re-index when a report or a decision changes, or the copilot will cite a rule this module no longer applies.

## 8. What this module needs from the network ML module

This is the one place we are the consumer.
Network quality drives churn in Libya, and a subscriber on a bad cell leaves; we do not model the network and will not duplicate that work.

The upGrad data this model trains on has no network fields at all, so this is a contract for the next version rather than something to send today.
Agreeing the names now is the cheap part.
What we would need, one row per subscriber per month, in an export beside the usage one:

| Field | Type | Meaning |
|---|---|---|
| `id` | text | The same pseudonymous subscriber ID as the usage export |
| `month` | integer | The month the row describes, as in the usage export |
| `dropped_call_rate_30d` | 0 to 1 | Share of that subscriber's calls dropped |
| `data_session_failure_rate` | 0 to 1 | Share of data sessions that failed |
| `cell_outage_hours_30d` | hours | Outage hours on the cells they used |
| `is_anomalous` | 0 or 1 | Optional, if the network module has an anomaly model |

Keyed by subscriber, not by cell: we never see a real cell, and mapping a subscriber to one is the operator's job, not ours.
Adding any of these fields means retraining and a new frozen champion, so it is a version 2 change: the test month was scored once and is spent (decisions 6 and 13).

For the antenna and cell placement module, we have nothing per cell to give.
Our outputs are per subscriber and per portfolio only.
"Customers at risk near this cell" needs the operator's subscriber-to-cell mapping, which this module does not hold; if the operator provides it, the join belongs on their side of the seam, not in either model.

## 9. Check it yourself before you write any code

`client.py` in this package is the worked example: it uses only the standard library, so copy it into your component rather than importing it.
`churn check-integration` runs it against a service and prints what came back, including the refusals:

```bash
uv run churn check-integration --url http://127.0.0.1:8000 --subscriber-id <a subscriber>
```

Run on 2026-09-27 against the service above: the 30,000-subscriber base and the demo campaign's copy with subscriber 70008 approved.

```
# Integration check of http://127.0.0.1:8000

## Health, without a key
- status: ok
- model: lightgbm-2026-09-19-ef9430fb, bundle loaded True, smoke prediction True
- serving 30000 subscribers and 1 approved offers from campaign 9dba975e547218ac0b11b593dee169b95a45e3a345438de12f53ea99771286de

## Chatbot, with the chatbot key
- /catalogue: 37 packages, for example HR5G_1 (Net 1 hour 5G) at 5.0 LYD, collected 2026-09-18
- /subscribers/70008/retention: DAY_50MB, approved 2026-09-27T03:23:02+00:00
- the chatbot may say: هديتك: نت 50MB لمدة يوم. [customer_message_ar]

## Copilot, with the copilot key
- /portfolio/summary: 30000 subscribers, risk available True, scored 2026-09-26T15:28:25+00:00
- by risk band: high 1209, medium 3594, low 22779, already_silent 2418
- LYD at risk: 308,864 (12-month scenario weighted by churn probability)
- release gate: True, 4 of 4 success thresholds passed
- /subscribers/70008/risk: high risk, probability 0.52419242304383, tier low, first reason "This month's share of the last two months' total minutes (50% = stable): 0%"

## Refusals, which every consumer has to handle
- the copilot's endpoint with the chatbot key: expected 403, got 403
- a chatbot endpoint with the copilot key: expected 403, got 403
- the copilot's subscriber lookup with the chatbot key: expected 403, got 403
- a chatbot endpoint with no key: expected 401, got 401
- a subscriber ID shaped like a phone number: expected 422, got 422

Every check passed.
```

The command exits 1 if any refusal did not happen, health is degraded, portfolio risk is unavailable or the model release gate has not passed.
Missing risk is printed as unavailable, and redirected output uses UTF-8 to preserve Arabic on Windows.

## 10. Changing this contract

A field added to a response is not a breaking change; a field removed or renamed is, and so is a status code that changes meaning.
If you need a field that is not here, ask before building around the gap.
Write it in the T20 ticket in [../TICKETS.md](../TICKETS.md), or tell Taha or Ali.

Include the endpoint, what you sent, what came back and what you expected.
Two components assuming different meanings for the same number is the failure this document exists to prevent, and it is much cheaper to catch now than in the integration week.
