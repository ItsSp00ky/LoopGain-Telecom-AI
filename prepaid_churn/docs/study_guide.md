# Study guide: the prepaid churn service and the customer chatbot

A guide for understanding everything in the prepaid customer module and the customer chatbot, well enough to explain, defend and change it.
Read it in order the first time; later, use the numbers and the questions at the end to revise.
Every claim here comes from the repository: the reports under `reports/`, the decisions in [decisions.md](decisions.md), the tickets in [../TICKETS.md](../TICKETS.md) and the code.
When this guide and a report disagree, the report wins, because reports are generated from the code.

## How to study it

1. Part 1 gives the big picture in ten minutes: what problem, what answer, what parts.
2. Parts 2 to 5 walk the churn service from raw data to an approved offer, one stage at a time.
3. Part 6 explains the customer chatbot.
4. Part 7 is how to run everything; Part 8 is the numbers to remember; Part 9 is the questions you will be asked; Part 10 is where things live; Part 11 is a self-test.

A good way to learn it: after each part, open the file it names and find the thing it describes.

## Part 1. The big picture

### The problem

In Libya most mobile lines are prepaid.
A prepaid customer who leaves cancels nothing: they simply stop using the line.
By the time the line is silent, no retention offer can reach them.
So the useful question is asked a month early:

> Which active prepaid customers are likely to stop using their line next month, and which approved operator offer should each one get?

That one sentence is the whole module (decision 17).

### The answer, in one picture

```
raw customer export
  -> check it (data contract)          -> clean it
  -> build monthly windows and labels  -> engineer features
  -> train and compare two models      -> calibrate, test once, freeze
  -> package the model (bundle)        -> score every active customer
  -> show them in the operator's money -> value tiers
  -> propose offers within a budget    -> a named person approves
  -> serve approved offers read-only   -> chatbot, copilot, dashboard
```

The first half runs once and produces a frozen model.
The second half, the business layer, runs on every new customer export.

### The parts you will talk about

| Part | What it is | Where |
|---|---|---|
| The churn model | LightGBM, calibrated, frozen on 19 September 2026 | `src/prepaid_churn/training.py`, `evaluation.py` |
| The business layer | Value tiers, retention offers, human approval, credit advice | `value.py`, `retention.py`, `campaign.py`, `advance.py` |
| The service | A read-only API that serves the results | `service.py`, `api.py` |
| The dashboard | Streamlit screens for a reviewer | `app/` |
| The customer chatbot | A Streamlit chat that answers customers from the service | `../assistants/` |

### Three rules that shape everything

1. **The test month is scored once.** The model was chosen, calibrated and given its thresholds on validation customers only, and the test customers were scored once, on 19 September 2026. Nothing may change because of the test result (hard rule, decisions 6 and 13).
2. **A person approves every offer.** The model proposes; a named reviewer approves; only approved rows ever reach a customer (decision 14).
3. **No language model decides.** No LLM sets an offer, a price or a credit limit; the chatbot and the copilot only read and explain (decision 17).

### Who did what

Taha and Ali built the module together; Taha owns the chatbot, the employee copilot and the integration with the rest of the team's platform, and Ali did the step-by-step review of every stage, the outside review and many fixes (decisions 24, 39 and 53).
The rest of the platform, GIS planning and network ML, belongs to the other teammates.

## Part 2. The data

### Customer behaviour: the upGrad dataset

- Source: the upGrad Telecom Churn Case Study on Kaggle, a public prepaid dataset from another market.
- 69,999 labelled customers with 172 columns, and 30,000 unlabelled customers that the module scores.
- Four months per customer: months 6, 7 and 8 of usage, recharges and packs, and a churn label for month 9.
- Why this one: it is prepaid and monthly, like the Libyan market. IBM Telco, Cell2Cell, the Iranian UCI data and KKBox were rejected as fictional, postpaid, too small or not telecom (decisions 1 and 5).
- Its limits, said openly: another market, only four months, education use only. What an operator would really use is the pipeline, retrained on its own customers (decision 11).

### The operator's data

- A real Libyan mobile operator's package list, pay-as-you-go tariffs and two emergency credit services, collected from its official website on 18 September 2026.
- 37 packages still on sale in 12 families; 20 retired "Mix" packages are kept in `data/operator/excluded.csv` with a reason, so a package never disappears silently (decision 31).
- The operator is not named anywhere in the module, at Ali's request, so the instructor learns the data is real and Libyan but not whose it is (decision 45).
- Each package records where its data volume comes from (`volume_source`): stated in the operator's own table (11 packages), read from the package name (17), reported by an earlier branch (6), or none (3) (decision 52).

### What "churn" means here

A customer churns in a month when that whole month has **no incoming calls, no outgoing calls and no mobile data**.
This matches how Kaggle's month-9 label was made, and computing the same rule on month 8 gives almost the same churn rate, which supports it.
Recharges do not count: many silent customers still recharged, and the label follows usage.

### The finding that shapes the product

59.9% of the customers who churned in month 9 were already silent in month 8.
Customers silent in month 8 churned at 77.9%; customers active in month 8 churned at 4.4%.
Predicting that a silent line stays silent is trivial and useless for retention, because those customers are already gone.
So **only customers active in the current month are scored** (decision 12), and the evaluated churn rate is about 4.35%, not the raw 10.19%.

## Part 3. The churn model, stage by stage

### T1 Profiling

`churn profile` measures the raw data before anything is built on it: missing values, ranges, the two inactivity definitions.
Missing values come in exactly two blocks (voice minutes and data), and in both cases missing means "nothing happened", so they become 0 (`reports/profile.md`).

### T2 The input contract

`schema.py` lists every column an export must have, its type and its rules; `docs/data_contract.md` is generated from that code, so the document cannot drift from what the code checks.
An operator integrates by producing a file that passes `churn validate` (decision 10).

### T3 Cleaning

Missing voice and data values become 0, recharge dates become "days before the month end", 13 constant columns are dropped, and negative revenue values are kept as billing adjustments (`clean.py`).

### T4 Windows, labels and the split

- **Window A**: months 6 and 7 are the features, month 8 is the label (computed by our usage rule). It is used for training and validation.
- **Window B**: months 7 and 8 are the features, month 9 is the label (Kaggle's). It is the test set, so the final score is on unseen customers in a later month.
- **Split by customer, 70/15/15**, stratified by the label, seed 42, so no customer appears in two sets.
- Result: train 45,858 customers (4.65% churn), validation 9,812 (4.61%), test 9,677 (4.35%).
- **No leakage**: features only ever use months up to the window's current month; month 9 never enters a feature.

Why two windows: a model that looks good on a random split can still fail next month; testing on a later month is the honest check.

### T5 Features

Each window gives 107 columns from its two months, and 19 engineered features are added, for 126.
Engineered features describe change: for example this month's share of the last two months' minutes (50% means stable), recharge trends, and days since the last recharge.
Only a few of them matter much: the four share features carry about 3% of the model's gain.

### T6 Training two models

- A **logistic regression** baseline, to prove the complex model is worth it.
- A **LightGBM** model with cautious hand-set parameters; its 288 trees were chosen by early stopping on training customers held aside, not on validation (decision 37).
- LightGBM won on validation: PR-AUC 0.458 against 0.336.

### T7 Calibration, thresholds and the one test

- **Calibration** (a sigmoid, Platt scaling) makes a score of 0.20 mean "about 20% of such customers churn". It matters because the retention step multiplies probabilities by money.
- **Risk bands** are fixed on validation: high from the best-F1 threshold, medium above the validation churn rate, low below it.
- **The test**: the test customers were scored once, on 19 September 2026, after everything was frozen.

The four **release checks** (decision 13), all passed on the test month:

| Check | Result | Required |
|---|---|---|
| PR-AUC above the baseline and at least 3 times the churn rate | 0.348 against 0.277; 8.0 times | yes |
| Share of leavers among the riskiest 10% ("capture") | 61.5% | at least 50% |
| Mean predicted churn against observed | 4.22% against 4.35% | within 1 percentage point |
| Beats the logistic regression baseline | on every measure | yes |

The checks were written after the single test run, at the instructor's request, so their pass is reported as a check, not as a pre-registered result.

**How sure are these numbers?** Resampling the test predictions 2,000 times puts LightGBM's PR-AUC between 0.301 and 0.400, and it beat the baseline in every resample; all four checks still pass at the unfavourable end of their ranges (decision 35).

### Key concepts, in plain words

- **PR-AUC (average precision)**: how well the model ranks leavers above stayers, focusing on the rare leavers. It is the primary metric because with 4.35% churn, a model that says "nobody leaves" is 95.65% accurate and useless. A random model's PR-AUC equals the churn rate (0.0435), so 0.348 is about 8 times better than random.
- **ROC-AUC**: the chance a random leaver is ranked above a random stayer; 0.891 here. It looks flattering when positives are rare, which is why PR-AUC leads.
- **Capture at 10%**: contact the riskiest 10% of customers and you reach 61.5% of next month's leavers, about six times what a random 10% would reach.
- **Calibration**: whether predicted probabilities match observed rates. Needed because offers are valued in money.
- **SHAP reasons**: exact per-customer contributions of each feature. A high- or medium-risk customer gets up to three reasons in plain words, for example "Outgoing roaming minutes this month: 82.9"; a low-risk customer gets one line saying the risk is low, so safe customers are not shown warning signs (decision 40).
- **Leakage**: using information from the future (month 9) or from the test set when building the model. It makes results look better than they will be in real use.

### What the model learned (the three findings)

1. Silence predicts silence (Part 2).
2. Roaming is the strongest signal: customers roaming in July went silent in August at 17.3%, against 2.6% for the rest. In Libya roaming would mean something else, one more reason to retrain on operator data.
3. Leavers fade first: customers who left in September fell from a median of 316 call minutes in July to 141 in August, while stayers rose from 346 to 365.

A limitation to know: the top signal is partly temporary absence (roamers are 52% of the churners, and 26% of customers silent in month 8 were active again in month 9), which the model card states.

### Experiments that were tried and removed

An LSTM over the monthly steps (PR-AUC 0.233, worse than LightGBM and even the baseline) and a model trained on synthetic customers (at most 45% of the real model's PR-AUC, and a detector told synthetic rows from real ones perfectly) were tried and removed, with one note kept in the model card (decision 44).
With only two monthly steps, the change between months is one subtraction that the features already give LightGBM, so a sequence model has nothing to learn.

### T8 The bundle and scoring

`churn bundle` packages the frozen champion with its version, its input contract fingerprint and a smoke check (it must predict a stored sample row correctly before it is used).
The bundle version is `lightgbm-2026-09-19-ef9430fb`, and a fresh clone rebuilds it byte for byte.
`churn score` writes one row per subscriber: calibrated probability, risk band, reasons, model version and time (`docs/output_contract.md`).
On the 30,000 unlabelled customers: 1,209 high, 3,594 medium, 22,779 low and 2,418 already silent.

## Part 4. The business layer

### T18 The operator view: money in LYD

The dataset's money is in another currency, so one rate converts it to LYD.
The rate comes from an assumed average revenue per user (ARPU) of 70 LYD a month, divided by the measured mean monthly recharge (537.17 source units), so 1 source unit is about 0.1303 LYD (decision 42).
The 70 LYD comes from the operator's Net 10 and Net 20 prices and the data share of Libyan operator revenue in a published market study; it is still an assumption, and an operator figure should replace it.

### T10 Value tiers

Five named tiers rank customers by recharges, tenure and engagement, with cutoffs frozen on the training customers (`tiers-v1-efc9739afad4`).
A clustering comparison (K-Means and Ward) found only weak natural groups, so the tiers are a reporting convention, not discovered segments.
The 12-month value scenario assumes constant risk and no comebacks; Ali found on validation that those assumptions do not hold, which undervalues high-risk customers, and T23 is open to fix it (decision 41).

### T11 Retention offers

For each eligible customer, each catalogue bonus they could use is valued:

> expected value = churn probability × 5% of leavers kept × 12-month value − delivery cost

- The 5% is an assumption, the same for every offer (decision 46); an earlier 10% for one package had nothing behind it.
- **Guardrails** remove offers that make no sense: the customer must use the service the bonus gives, low-risk customers get nothing, and silent customers are not targeted.
- The best positive offers are funded greedily within a budget.
- A 1,000 LYD campaign over the 30,000 customers proposes 3,643 offers (mostly the 1 LYD morning pass and the 0.5 LYD day pack) for 962.53 LYD.
- **A permanent control group** (the same held-out customers in every campaign, 2,965 of them) receives nothing, so the real effect of offers can be measured one day (decision 43). Without it, every claim of effectiveness is an assertion.
- The comparison of the plan against a simple policy favours the plan by construction, and the reports say so.

### Human approval and release

`churn decide` writes proposals to a campaign directory; nothing reaches anyone yet.
A reviewer approves or rejects by name (`churn approve`, or on the dashboard); the review is locked and logged.
Only approved rows go to `released.csv`, which is the only thing the service serves to the chatbot.

### The customer message

The policy's reason ("positive value under the stated retention assumptions") is for staff.
A customer hears a separate message written from the catalogue row alone, for example "هديتك: الصبح، إنترنت ومكالمات لا محدودة من 06:00 إلى 11:00 لمدة يوم." ("Your gift: Morning, unlimited data and calls from 06:00 to 11:00 for a day."), which fits one Arabic SMS (decision 51).

### T19 Emergency credit advice

The operator offers airtime advances (1, 3 or 5 LYD) and a 5 LYD data advance, repaid from the next recharge; the smallest recharge card is 5 LYD.
The advice reads the card a customer would actually buy, never below 5 LYD, from the average of their two months, and advises a rung that leaves them usable balance after repayment (decisions 49 and 50).
About 63% of recharging customers are on the smallest card and are advised the 3 LYD airtime rung, about 32% can also carry the data advance, and about 5% get no advice (`reports/emergency_credit.md`).
It is advice, not a grant: no credit is given without a person.

## Part 5. Serving the results

### The API service (T15)

A read-only FastAPI service with five GET endpoints:

| Endpoint | Key | Answers |
|---|---|---|
| `/health` | none | Whether the model predicts and which outputs are served |
| `/catalogue` | chatbot | Every package on sale, with where its volume comes from |
| `/subscribers/{id}/retention` | chatbot | The approved offer for one customer, as a customer message, or 404 |
| `/portfolio/summary` | copilot | Customers and LYD at risk by band and tier, and the test results |
| `/subscribers/{id}/risk` | copilot | One customer's risk, reasons and value, for an employee |

Why a service and not a shared package: the approval step cannot be bypassed, the chatbot and the copilot see different things, and the storage behind it can change without breaking them (decisions 10, 21 and 25).

Protections worth knowing:

- **Two keys**: the chatbot key is refused (403) on the copilot's endpoints, so the chatbot can never reach a churn probability.
- **Pseudonymous IDs**: an ID shaped like a Libyan phone number is refused (422); operators hash numbers before export.
- **Read-only**: every route is a GET, and a test checks there is no other method.
- **A 404 hides the reason**: no campaign, no proposal, not reviewed and rejected all look the same, so a customer is never told an offer was considered and refused.
- **The portfolio is checked on load**: probabilities between 0 and 1, known bands and tiers, and the same model version as the loaded bundle, or `/health` is degraded (decision 52).
- **A new approval reaches the chatbot without a restart**: the service reads the campaign again when a review changes it (decision 47).

### The dashboard (T14)

A Streamlit app for a reviewer: Overview (customers and LYD at risk), Subscriber (one customer, with the emergency credit advice), Campaign builder (propose and approve by name), Message preview and Released.
It is the only place, besides `churn approve`, where anything is written: a named review and a proposed campaign (decision 34).

## Part 6. The customer chatbot

### What it does

It answers two questions for a prepaid customer, in Arabic (including the Libyan dialect) or English: **which of the operator's packages fit me, and is there an offer waiting for me?**
It answers only from the service; it never invents a package, a price, a volume or an offer.

### Where it lives

`assistants/` at the repository root, its own project, shared with the future employee copilot (decision 54):

| File | What it does |
|---|---|
| `chatbot_app.py` | The Streamlit chat screen |
| `src/assistants/llm.py` | One turn: the model picks tools, the code runs them, the answer is checked |
| `src/assistants/chatbot_tools.py` | The three tools, the rules given to the model, the safe answers, and `answer()` |
| `src/assistants/grounding.py` | The number check and the phone-number check |
| `src/assistants/language.py` | Which language a text is in |
| `src/assistants/service_client.py` | A verified copy of the module's API client |
| `src/assistants/ui.py` | The shared look: header, right-to-left Arabic, the "What I looked up" panel |
| `src/assistants/evaluate.py`, `eval/chatbot_questions.toml` | The 21-question evaluation on the real model |
| `.env` | The keys (git-ignored); `.env.example` lists them |

### The model

GPT-OSS 120B on Groq, a hosted model, with low reasoning effort and temperature 0.
Nothing was trained or fine-tuned: the model only chooses a tool and phrases what came back.
Llama 3.3 70B was the first choice, but Groq retired it for free accounts on 16 August 2026.
The free plan allows about 8,000 tokens a minute and 200,000 a day, so a turn takes about 20 seconds and a day holds about sixty turns: enough for a demo, not for real customers.

### One turn, step by step

1. **Code prepares the turn.** It detects the language of the message, knows whether the customer is signed in, and notices whether the message names someone else's account or phone number.
2. **The model picks a tool.** It sees the rules and the three tools.
3. **The tool runs in code** against the service:
   - `find_packages` filters and sorts the catalogue in Python (the model never compares prices) and returns up to 10 packages, 5 by default, with how many matched and in what order;
   - `my_offer` takes no arguments: the subscriber comes from the sign-in, so the model can neither choose nor see whose offer it reads, and it exists only when someone is signed in;
   - `find_service_point` says the shop locations are not available yet.
4. **The model phrases the answer** from what the tool returned.
5. **Code checks the answer** before anyone reads it:
   - every number must appear in a tool result, the customer's message or an earlier checked answer, or the answer is replaced by a safe one built only from the tool results;
   - an answer holding a Libyan phone number is replaced the same way, even if the customer typed it;
   - if the service or the model fails, the customer is told it is not available right now, never a guess.
6. **The screen shows the answer** with "What I looked up": every tool call and exactly what it returned.

### What the model sees, and what it does not

- Each package arrives as one line in the customer's language: the price in dinars for an Arabic reply and in LYD for an English one, the validity from its hours, and a data volume only as the operator states it; a volume from the package name says so, and any other is "not stated by the operator".
- An offer arrives as the service's customer message only; the policy's reason never reaches the model.
- The subscriber ID, the campaign ID and any churn probability never reach the model or Groq.

### Why these guards are in code, not in the prompt

A prompt is advice to the model; code is a guarantee.
Each code guard exists because a real run showed the model getting it wrong with only a written rule:

| What happened in a real run | What the code does now |
|---|---|
| An English question was answered in Arabic | The code detects the language and tells the model which one to use |
| A customer who was not signed in was told there was no offer | Without a sign-in there is no offer tool at all |
| Asked about another customer, it answered for the signed-in one without saying so | A fixed sentence says it only checks your own account |
| A request for the best 10 packages showed 5 | The customer chooses up to 10, and "best" is asked about or stated |
| Arabic lines were scrambled around "LYD" | Prices read "دينار" and Arabic runs right to left on screen |
| The digits inside a package code let an invented "1" pass | Identifiers no longer count as sources for the number check |

### How it is tested

- **64 automated tests** with hand-made data and a scripted model, so none calls the model or the network; one fails if the client copy drifts from the module's.
- **The evaluation**: 21 questions on the real model against the live service, passed 21 of 21 on 28 September 2026 (`assistants/reports/chatbot_eval.md`).
  - Packages (6): the right packages, in the customer's language, as many as asked.
  - Offers (5): the approved gift message; "nothing today" without one; a sign-in request without a sign-in.
  - Attacks (6): no discount, no other customer's offer, no talk of leaving, no phone number repeated.
  - Out of scope (4): balance, faults and shops sent to customer service.
- Each answer is checked for the expected tool, the expected words, nothing forbidden (risk wording, the operator's name, an unasked percentage) and the right language, and it must not have needed the safe answer.
- Reading the answers, not only the checks, is what found most of the fixes above.

### Its limits

- Shop locations wait for a list of the operator's shops.
- About 20 seconds a turn on the free plan.
- The subscriber ID typed on screen stands in for a real login.
- For a volume taken from a package name, the model sometimes drops the words "from the package name".
- The customer's words and the tool results go to Groq; a real operator would need a model it controls or a contract that covers customer messages.

## Part 7. How to run everything

From `prepaid_churn/`, rebuild every artifact and report (about four minutes):

```bash
uv sync
uv run churn build-dataset
uv run churn train
uv run churn evaluate --chosen-at 2026-09-19
uv run churn uncertainty
uv run churn bundle
uv run churn score
uv run churn operator-view
uv run churn fit-tiers
uv run churn tiers
uv run churn advance
```

Propose and approve a campaign:

```bash
uv run churn decide --output-dir artifacts/campaigns/campaign-001
uv run churn approve --proposals artifacts/campaigns/campaign-001/proposals.json --reviewer taha
```

Start the service (the two keys must be long, different, and the same ones as in `assistants/.env`):

```bash
uv run churn serve --campaign-dir artifacts/campaigns/ui-2026-09-22-200
```

The reviewer dashboard: `uv run streamlit run app/Home.py`.
The chatbot, from `assistants/`: `uv run streamlit run chatbot_app.py`; in campaign `ui-2026-09-22-200`, subscriber 70016 has an approved offer and 70017 has none.
The chatbot's checks: `uv run pytest`; its evaluation: `uv run python -m assistants.evaluate chatbot`.

## Part 8. Numbers to remember

| Number | Meaning |
|---|---|
| 69,999 and 30,000 | Labelled customers, and unlabelled customers scored |
| 59.9% | Month-9 leavers already silent in month 8 |
| 77.9% and 4.4% | Churn of customers silent and active in month 8 |
| 45,858 / 9,812 / 9,677 | Train, validation and test customers |
| 4.35% | Churn in the test month |
| 126 | Features (107 window columns and 19 engineered) |
| 0.458 against 0.336 | Validation PR-AUC, LightGBM against the baseline |
| 0.348 against 0.277 | Test PR-AUC, LightGBM against the baseline |
| 0.301 to 0.400 | The 95% range of the test PR-AUC |
| 0.891 | Test ROC-AUC |
| 61.5% | Leavers reached by contacting the riskiest 10% |
| 4.22% against 4.35% | Mean predicted churn against observed |
| 19 September 2026 | The single test run and the frozen model |
| `lightgbm-2026-09-19-ef9430fb` | The bundle version |
| 1,209 / 3,594 / 22,779 / 2,418 | High, medium, low and already silent among the 30,000 |
| 70 LYD | Assumed ARPU behind the LYD rate |
| 5% | Assumed share of leavers kept by any offer |
| 3,643 for 962.53 LYD | Offers in a 1,000 LYD campaign |
| 2,965 | Customers in the permanent control group |
| 37 packages, 12 families | The operator's catalogue on sale |
| 11 / 17 / 6 / 3 | Package volumes stated / from the name / reported / none |
| 5 | GET endpoints of the service |
| 475 | Automated tests of the churn module |
| 64 and 21 of 21 | Chatbot tests, and evaluation questions passed |
| about 20 seconds | One chatbot turn on the free plan |

## Part 9. Questions you will be asked

**Why not let the AI decide the offer?**
Because an offer is money, and a language model cannot be held to a budget or a rule; ours is chosen by a calibrated model with guardrails, checked against a budget and approved by a named person, and the chatbot only repeats that decision.

**Your data is not Libyan. Is this useful?**
The operator data (packages, prices, credit rules) is real and Libyan; the customer behaviour is public data from another market because no Libyan customer records were available. The value is the pipeline: an operator retrains it on its own export, which only has to pass the data contract.

**Why PR-AUC and not accuracy?**
With 4.35% churn, predicting "nobody leaves" is 95.65% accurate and finds nobody; PR-AUC measures how well the rare leavers are ranked, and ours is about 8 times random.

**How do you know the results are not overfitted?**
The test set is different customers in a later month, scored once after everything was frozen, and resampling puts the PR-AUC between 0.301 and 0.400 with the model beating the baseline in every sample.

**Why only active customers?**
Most leavers are already silent the month before; predicting them is trivial and too late for any offer.

**Did deep learning win?**
No: the LSTM reached PR-AUC 0.233 against 0.348, because two monthly steps are not a history.

**How do you know an offer works?**
We do not yet; the 5% is an assumption, and the permanent control group exists so a real campaign can measure it.

**Is the chatbot RAG?**
No. It is grounded on live tool calls: every number it says came from the service in that turn. Retrieval over documents is planned for the employee copilot, not the chatbot.

**What stops the chatbot inventing a price?**
Code: every number in an answer must appear in what a tool returned, or the answer is replaced by a safe one built from the tool results.

**Can the chatbot leak a customer's churn risk?**
No. Its key is refused on the risk endpoints, so it cannot even ask for one.

**Why is the operator not named?**
The team chose to show the instructor that the data is real and Libyan without saying whose it is (decision 45).

## Part 10. Where things live

| Path | What |
|---|---|
| `prepaid_churn/src/prepaid_churn/` | The module's code, one file per stage |
| `prepaid_churn/reports/` | Generated reports with every number (committed) |
| `prepaid_churn/docs/model_card.md` | Intended use, data, metrics, limits, ethics |
| `prepaid_churn/docs/decisions.md` | Why every choice was made, numbered |
| `prepaid_churn/docs/integration.md` | The guide for the chatbot and copilot owners |
| `prepaid_churn/docs/operator.md` | The operator's catalogue and market facts |
| `prepaid_churn/TICKETS.md` | The work plan; the Handoff at the top is the current state |
| `prepaid_churn/app/` | The reviewer dashboard |
| `assistants/` | The customer chatbot (and the copilot next) |
| `assistants/reports/chatbot_eval.md` | The latest chatbot evaluation |

Decisions worth reading first: 1, 5 and 12 (data and who is scored), 13 and 14 (release checks and human approval), 17 (the platform and the no-LLM rule), 35 (uncertainty), 42 to 46 (the business assumptions and the operator's anonymity), 51 and 52 (the customer message and stated volumes), 54 (the chatbot).

## Part 11. Self-test

Answer without looking, then check the part in brackets.

1. What exactly is "churn" in this module, and why is recharging not enough to count as active? (Part 2)
2. Why are silent customers not scored? Give the two numbers that justify it. (Part 2)
3. What is in window A and window B, and why is the test in a later month? (Part 3, T4)
4. Name the four release checks and whether they were written before or after the test. (Part 3, T7)
5. What does calibration change, and why does the retention step need it? (Part 3)
6. Why does a low-risk customer get no reasons? (Part 3, SHAP)
7. Write the expected-value formula for an offer and name its two assumptions. (Part 4, T11)
8. What is the control group for, and why is it the same customers every time? (Part 4)
9. Which endpoints can the chatbot call, and what happens if it tries another? (Part 5)
10. Why does `my_offer` take no arguments? (Part 6)
11. What happens to an answer that contains a number no tool returned? (Part 6)
12. Name three things the chatbot does in code because a written rule was not enough. (Part 6)
13. How long does a chatbot turn take, and why? (Part 6)
14. How would an operator retrain the module on its own customers? (Parts 2 and 7)
