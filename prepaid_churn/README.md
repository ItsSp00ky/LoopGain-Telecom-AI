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

## Development

```bash
uv run ruff check
uv run ruff format --check
uv run pytest
```
