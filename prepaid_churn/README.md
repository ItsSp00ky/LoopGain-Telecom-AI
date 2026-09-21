# Prepaid Churn

Customer module of the Loop Gain capstone (Samsung Innovation Campus): churn risk, value and retention offers for prepaid subscribers of Almadar Aljadid in Libya.
Churn means a subscriber goes inactive: no incoming or outgoing calls and no mobile data in a month.
The model learns from real prepaid customers (upGrad data); prices, packages and money are Almadar's (decision 16).
The team's chatbot and copilot use its outputs (decision 17).

**New here (for example Ali):** read the Handoff section of [TICKETS.md](TICKETS.md) first; it says how to rebuild everything and what comes next.

- Plan, status and handoff notes: [TICKETS.md](TICKETS.md).
- What the model is, what it may not be used for, and its limits: [docs/model_card.md](docs/model_card.md).
- Why things are the way they are: [docs/decisions.md](docs/decisions.md).
- Working with Claude on this module: [CLAUDE.md](CLAUDE.md).

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run churn --help
```

## Data

The model is developed on the upGrad "Telecom Churn Case Study" prepaid dataset.
The files are already in the repo at `data/raw/` (`train.csv`, `test.csv`, `data_dictionary.csv`), so a fresh clone is ready to run.

Source: the Kaggle competition [Telecom Churn Case Study Hackathon](https://www.kaggle.com/competitions/telecom-churn-case-study-hackathon-c-69/data).
The data is for educational use under that competition's rules, which forbid sharing it outside a Kaggle team.
The team chose to keep it in this private repo anyway (see [decision 9](docs/decisions.md)); do not copy it anywhere public.

## Commands

| Command | Ticket | What it does |
|---|---|---|
| `uv run churn profile` | T1 | Profiles `data/raw/train.csv` and writes `reports/profile.md` |
| `uv run churn validate [--input <file>]` | T2 | Checks an export against the [data contract](docs/data_contract.md) |
| `uv run churn contract` | T2 | Regenerates `docs/data_contract.md` from the code |
| `uv run churn build-dataset [--high-value]` | T4 | Validates, cleans and builds train, validation and test windows in `data/processed/` |
| `uv run churn train` | T6 | Trains logistic regression and LightGBM into `artifacts/models/` |
| `uv run churn evaluate` | T7 | Calibrates and freezes the champion on validation, scores the test month and stores the release gate (decision 13) |
| `uv run churn bundle` | T8 | Packages a champion that passed its release gate into `artifacts/bundle/` |
| `uv run churn score [--input <file>]` | T8 | Writes one [output contract](docs/output_contract.md) row per subscriber to `artifacts/scores/scores.csv` |
| `uv run churn output-contract` | T8 | Regenerates `docs/output_contract.md` from the code |
| `uv run churn check-integration --subscriber-id <id>` | T20 | Calls a running service the way the chatbot and the copilot do, and reports what came back |
| `uv run churn sequence-benchmark` | T12 | Trains a Keras LSTM and compares it with the champion on the frozen test window (needs the experiments group) |
| `uv run churn almadar-view [--input <file>]` | T18 | Shows every customer in Almadar money and packages; writes `reports/almadar_view.md` |
| `uv run churn fit-tiers` | T10 | Fits and saves value cutoffs from `train.parquet` only; writes `reports/tiers.md` and clustering plots |
| `uv run churn tiers [--input <file>]` | T10 | Extends live churn scores with frozen value tiers and 12-month revenue scenarios in `artifacts/scores/tiers.csv` |
| `uv run churn tiers --tiers-only` | T10 | Assigns tiers without a churn bundle; marks risk-dependent value estimates unavailable |
| `uv run churn decide` | T11 | Proposes catalogue bonuses under a campaign budget and writes `reports/decisions.md`; releases nothing |
| `uv run churn approve --proposals <file> --reviewer <name>` | T11 | Approves pending proposals and exports approved rows only; `--reject` records rejection |
| `uv run churn advance` | T19 | Advises an emergency credit limit per customer and writes `reports/emergency_credit.md`; grants nothing |
| `uv run churn serve` | T15 | Serves the released outputs read-only to the chatbot and copilot; needs both API keys |
| `uv run streamlit run app/Home.py` | T14 | Opens the four demo screens over the released outputs; the only screen that writes is the named approval |

Full pipeline from a fresh clone, about a minute (the processed data, models and scores are git-ignored and rebuilt):

```bash
uv sync
uv run churn build-dataset
uv run churn train
uv run churn evaluate --chosen-at 2026-09-19
uv run churn bundle
uv run churn score
uv run churn almadar-view
uv run churn fit-tiers
uv run churn tiers
```

`--chosen-at 2026-09-19` keeps the date the champion was frozen.
The rebuild reproduces the frozen champion byte for byte, so the bundle is `lightgbm-2026-09-19-ef9430fb` and `git status` shows no changed report.
Checked again on 2026-09-21 from a fresh clone of `Ali_Branch`: same bundle version, same tier artifact `tiers-v1-cd15525cb3ef`, and no committed report changed.

The last two commands build the value layer that the retention decisions (T11), the service (T15) and the demo app (T14) read.
To go further, `uv run churn decide --output-dir artifacts/campaigns/campaign-001` proposes offers and `uv run churn approve` releases the ones a reviewer accepts.
The Almadar packages and market facts are in `data/almadar/` ([docs/almadar.md](docs/almadar.md)).

## Value tiers without new operator data

The T10 layer uses the existing upGrad behaviour and the assumed T18 LYD conversion.
From `prepaid_churn/`, with the locked environment installed:

```bash
uv run churn build-dataset
uv run churn fit-tiers
uv run churn tiers --tiers-only
```

`fit-tiers` reads only `data/processed/all/train.parquet`, using window A (months 6 and 7).
The existing customer split stays unchanged; the value layer never reads labels or validation/test parquet files.
`artifacts/tiers/tiers.json` freezes dimension and composite cutoffs, the LYD rate and a content-based version.
Keep that artifact when scoring future exports; never refit on the scored batch.
Missing activity follows the input contract, tied customers stay together, and every valid subscriber gets one tier.
Already-silent subscribers receive a tier too, but no risk-based revenue estimate.

With the existing gated churn bundle available, run:

```bash
uv run churn tiers
```

This scores the same input export with T8, then adds `value_tier`, dimension scores and `value_12m_base_lyd` with low/high sensitivity scenarios.
It does not train, recalibrate or reevaluate the churn model.
No real churn bundle is committed; `--tiers-only` allows value work on a fresh checkout without repeating the spent test evaluation.
The 12-month amounts assume a constant monthly churn hazard and spend, and are explicitly revenue scenarios rather than validated CLV, profit or causal offer savings.
Their assumptions and the training-only rules-versus-clusters comparison are in [reports/tiers.md](reports/tiers.md).
The CSV columns are defined in [docs/output_contract.md](docs/output_contract.md).

## Retention proposals and human review

T11 uses the real catalogue, frozen risk and value outputs, and explicitly assumed costs and retention effects from `data/almadar/retention.toml`.
It grants catalogue products as bonuses, without changing retail prices.
With the existing gated churn bundle available:

```bash
uv run churn decide --budget 1000 --output-dir artifacts/campaigns/campaign-001
```

Inspect `artifacts/campaigns/campaign-001/decisions.csv` before reviewing.
The authoritative `proposals.json` stores the input rows, catalogue and policy snapshots, decisions and later review events.
Editing a CSV cannot approve an offer.
Each campaign needs a new output directory so earlier decisions and approvals are preserved.

Approve or reject a specific pending subscriber, or omit `--subscriber-id` to review all pending proposals:

```bash
uv run churn approve --proposals artifacts/campaigns/campaign-001/proposals.json --reviewer "Reviewer name" --subscriber-id "0001" --note "Reviewed"
uv run churn approve --proposals artifacts/campaigns/campaign-001/proposals.json --reviewer "Reviewer name" --subscriber-id "0002" --reject --note "Not suitable"
```

Repeat `--subscriber-id` for multiple subscribers.
Only approved rows enter `released.csv`; pending, rejected, holdout and no-offer rows never enter it.
`review_log.jsonl` records each decision with reviewer, UTC time, note and campaign fingerprint.
Reviews resolve pending proposals once; changing a reviewed decision requires a new campaign, and this CLI does not revoke already released offers.
`--refresh` rebuilds derived CSV and log files from the authoritative JSON after an interrupted write, without reviewing any pending rows.
A named reviewer is still required for that command.
The files are local review bookkeeping, not authenticated identity or a sending service; access control belongs to T15.

Without a real churn bundle, run the explicit readiness mode:

```bash
uv run churn decide --tiers-only --output-dir artifacts/campaigns/readiness-001
```

This produces one decision row per subscriber, with no offers and unavailable risk estimates.
The committed [retention report](reports/decisions.md) records the 30,000-customer readiness run, all cost/effect assumptions, and the equal-spend comparison.
Zero proposals in that run are not evidence of campaign effectiveness.
The full positive-proposal, budget, holdout and approval paths are tested on hand-made data.
No real-data churn evaluation needs to be repeated for T11.

## Integration service for the chatbot and copilot

The chatbot and the copilot call this service; they never import the package or read its files.
It is read-only: every route is a GET, and nothing can be created, changed or approved through it.
An offer appears only after a named reviewer approved it with `churn approve`.

Both API keys are required and have no default, so set them first:

```bash
export PREPAID_CHURN_CHATBOT_KEY="<a long random string>"
export PREPAID_CHURN_COPILOT_KEY="<a different long random string>"
uv run churn serve
```

On Windows PowerShell, use `$env:PREPAID_CHURN_CHATBOT_KEY = "..."` instead of `export`.

| Endpoint | Key | What it returns |
|---|---|---|
| `GET /health` | none | Whether the bundle loads and predicts, and which outputs are being served |
| `GET /catalogue` | chatbot | Every Almadar package with its collection date |
| `GET /subscribers/{id}/retention` | chatbot | The approved offer and its reason, or 404; never a churn probability |
| `GET /portfolio/summary` | copilot | Customers and LYD at risk by risk band and value tier, with the model's test metrics |
| `GET /subscribers/{id}/risk` | copilot | One subscriber's risk, the model's reasons and their value tier; never reachable with the chatbot key |

Each key is accepted only on its own endpoints, so a leaked chatbot key cannot read the portfolio.
Subscriber IDs are pseudonymous: an ID shaped like a Libyan mobile number is refused, and `prepaid_churn.privacy.pseudonymize` is the supported way for an operator to hash numbers before exporting them.
The OpenAPI page at `/docs` is generated from the response models, so it is the integration documentation for the other teams.

Outputs are read once when the service starts, so restart it after a new `churn approve` release.
`/health` reports the campaign it is holding, so you can see what is being served.
Without a bundle, `/health` reports `degraded` and the portfolio reports `risk_available` false with every `lyd_at_risk` null, which is the state of this checkout.

## Integration guide for the other components

[docs/integration.md](docs/integration.md) is the guide for the chatbot, copilot, network ML and antenna owners.
It has the endpoints with real responses, the grounding rules for the components that use a language model, which documents the copilot may index, and the field contract for the per-subscriber network quality this module would need from network ML.

`src/prepaid_churn/client.py` is the worked example, written to be copied into their repositories: it uses only the standard library, so it adds no dependency on either side.
With a service running, the check calls every endpoint and every refusal a consumer has to handle:

```bash
uv run churn check-integration --url http://127.0.0.1:8000 --subscriber-id <a subscriber>
```

It prints what each consumer sees and exits 1 if a refusal did not happen, so the seam is checked rather than described.
Run on 2026-09-21 against a service holding the 30,000-subscriber base and a reviewed campaign: status ok, 57 packages, the approved offer for one subscriber, 176,494 LYD at risk, and all four refusals correct.

## Syllabus experiments

The two graded experiments live behind a separate dependency group, so a fresh clone stays small:

```bash
uv sync --group experiments
uv run churn sequence-benchmark
```

T12 trains a Keras LSTM over the two monthly steps of each window and scores it once on the same frozen test window as T7.
It loses, as two monthly steps predict: PR-AUC 0.2326 against LightGBM's 0.3477, and it fails two of the four release checks.
The comparison, the thresholds and the caveats are in [reports/sequence_benchmark.md](reports/sequence_benchmark.md), and decisions 27 and 28 record why the answer is kept as it came out.
Keras runs on the torch backend; SDV (T13) is deliberately not in this group, because it caps pandas below 3 and would downgrade the environment the champion was frozen in.

## Demo app

Four screens over what the pipeline wrote, for showing the module to someone.

```bash
uv run streamlit run app/Home.py
```

| Screen | What it shows |
|---|---|
| Home | The base, expected churners and revenue at risk, and what is not built yet |
| Overview | Customers and LYD at risk by risk band and value tier, with the model's test results |
| Subscriber | One customer: risk, plain-language reasons, value tier, the Almadar bundle held and the proposed offer |
| Campaign builder | What the guardrails removed, the holdout, cost and value, the equal-spend comparison, and approve or reject under your name |
| Message preview | The Arabic message an approved customer would receive, and how many SMS parts it actually costs |

By default it reads the first campaign in `artifacts/campaigns/retention`.
To show another one, name it before starting:

```bash
export PREPAID_CHURN_CAMPAIGN_DIR="artifacts/campaigns/campaign-001"
export PREPAID_CHURN_PORTFOLIO="artifacts/scores/tiers.csv"
```

The app recomputes nothing.
The only thing it writes is a review, through the same locked and audited path as `churn approve`, and only approved rows reach `released.csv`.
The budget slider on the campaign screen is a preview over that campaign's own stored inputs: it is never written and nothing in it can be approved, so use `churn decide --budget` into a new directory to make a different budget real.

Without a gated bundle, every screen says so and leaves the risk figures blank rather than showing zero.

One thing the message screen is for: a single Arabic character forces an SMS into UCS-2, where one part is 70 characters instead of 160.
The current approved message is 102 characters, so it sends, and bills, as two parts.

## Emergency credit advice

Almadar sells two emergency credit products: an airtime advance of 1, 3 or 5 LYD, and a
flat 5 LYD data advance for 2 GB over 72 hours.
Both are offered when the balance is nearly empty, so the eligible population is selected
on being broke.

```bash
uv run churn advance
```

One rule decides the advice: never advise a debt above 0.6 of the customer's typical
top-up, so that clearing it still leaves usable balance.
It advises only amounts the operator actually sells, it estimates no probability of
repayment, and it grants nothing.
A limit reaches a customer only if a person approves it, exactly as a retention offer does.

The finding that motivates the rule is in [reports/emergency_credit.md](reports/emergency_credit.md):
the smallest recharge card, the data advance and the top airtime rung are all 5 LYD, so
clearing either debt with one card returns the customer to a zero balance and buys them
nothing.

On the 30,000 unlabeled customers the result says more about the product than about the
rule. This base tops up often in very small amounts, so 46.1% cannot carry even the 1 LYD
advance and still have something left, and the flat 5 LYD data advance suits 4.65%.
The report states every assumption, including how much the answer moves if a different
statistic stands in for the customer's typical top-up.

## Development checks

```bash
uv run ruff check
uv run ruff format --check
uv run pytest
```
