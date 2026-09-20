# Prepaid Churn

Customer module of the Loop Gain capstone (Samsung Innovation Campus): churn risk, value and retention offers for prepaid subscribers of Almadar Aljadid in Libya.
Churn means a subscriber goes inactive: no incoming or outgoing calls and no mobile data in a month.
The model learns from real prepaid customers (upGrad data); prices, packages and money are Almadar's (decision 16).
The team's chatbot and copilot use its outputs (decision 17).

**New here (for example Ali):** read the Handoff section of [TICKETS.md](TICKETS.md) first; it says how to rebuild everything and what comes next.

- Plan, status and handoff notes: [TICKETS.md](TICKETS.md).
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
| `uv run churn almadar-view [--input <file>]` | T18 | Shows every customer in Almadar money and packages; writes `reports/almadar_view.md` |
| `uv run churn fit-tiers` | T10 | Fits and saves value cutoffs from `train.parquet` only; writes `reports/tiers.md` and clustering plots |
| `uv run churn tiers [--input <file>]` | T10 | Extends live churn scores with frozen value tiers and 12-month revenue scenarios in `artifacts/scores/tiers.csv` |
| `uv run churn tiers --tiers-only` | T10 | Assigns tiers without a churn bundle; marks risk-dependent value estimates unavailable |
| `uv run churn decide` | T11 | Proposes catalogue bonuses under a campaign budget and writes `reports/decisions.md`; releases nothing |
| `uv run churn approve --proposals <file> --reviewer <name>` | T11 | Approves pending proposals and exports approved rows only; `--reject` records rejection |

Full pipeline from a fresh clone, about a minute (the processed data, models and scores are git-ignored and rebuilt):

```bash
uv sync
uv run churn build-dataset
uv run churn train
uv run churn evaluate --chosen-at 2026-09-19
uv run churn bundle
uv run churn score
uv run churn almadar-view
```

`--chosen-at 2026-09-19` keeps the date the champion was frozen.
The rebuild reproduces the frozen champion byte for byte, so the bundle is `lightgbm-2026-09-19-ef9430fb` and `git status` shows no changed report.
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

## Development checks

```bash
uv run ruff check
uv run ruff format --check
uv run pytest
```
