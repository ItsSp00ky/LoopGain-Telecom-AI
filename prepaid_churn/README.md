# Prepaid Churn

Churn risk model for prepaid telecom subscribers, built for the Loop Gain capstone (Samsung Innovation Campus).
Churn means a subscriber goes inactive: no incoming or outgoing calls and no mobile data in a month.

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
| `uv run churn evaluate` | T7 | Calibrates and freezes the champion on validation, then scores the test month once |

Full pipeline from a fresh clone: `uv sync`, then `build-dataset`, `train` and `evaluate`.

## Development

```bash
uv run ruff check
uv run ruff format --check
uv run pytest
```
