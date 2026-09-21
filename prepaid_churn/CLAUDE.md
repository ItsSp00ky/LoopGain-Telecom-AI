# Instructions for Claude sessions on the prepaid churn module

Read this first, then [TICKETS.md](TICKETS.md) (start with its Handoff section), then [docs/decisions.md](docs/decisions.md).
When porting anything from Ali's `Ali_Branch`, also read [docs/ali_branch_merge.md](docs/ali_branch_merge.md).

## Context

- Samsung Innovation Campus (SIC) capstone, Team Loop Gain, repo `ItsSp00ky/LoopGain-Telecom-AI`.
- This folder is the customer module: churn risk, value, retention offers and their integration, for **prepaid** subscribers of Almadar Aljadid in Libya (decision 16).
- The real goal is the team's one platform: GIS planning, network ML, this module, a customer chatbot and an employee copilot (decision 17).
  Every ticket is judged by whether it helps that integration, and the customer MVP comes before any extra experiment.
- Taha and Ali Marghem work on it together, each with their own session.
  Both branches met on 2026-09-21: `Ali_Branch` was built on this tree, so `tahaDev` was fast-forwarded to it and is now the only branch (decision 24).
  The repo is the only shared memory: anything decided in a chat must be written into TICKETS.md or docs/decisions.md.
- The module must stay ready to integrate with the team's customer chatbot and employee copilot through fixed input and output contracts (decision 10), and ready to retrain on a Libyan operator's own data (decision 11).
- The older `customer_churn_prediction/` folder is Ahmed's earlier module.
  It was audited and is not reused (see decision 1); do not edit it or build on it.

## Hard rules

- Work on `tahaDev`, the branch both of us share (decision 24).
  Pull before you start, claim a ticket by writing your name in its Owner field, and push when it is done.
  Do not pull or merge `main`, and push only what this module owns.
- The raw Kaggle files in `data/raw/` are committed on purpose (decision 9); do not remove them.
  Never commit `data/processed/` or `artifacts/`, and never add another dataset without a decision entry.
- No leakage: features may only use months up to and including the window's "current month"; month 9 never enters features.
- Model selection, calibration and thresholds use validation customers only.
  The test customers are evaluated once, after everything is frozen.
  That evaluation happened on 2026-09-19 (T7); never change a model, feature or threshold because of test results.
- Do not reopen settled decisions in TICKETS.md without writing a new entry in docs/decisions.md that explains why.
- Prefer the simplest thing that works; no new infrastructure (tracking servers, feature stores, containers) without a decision entry.
- Ask before implementing anything not covered by a ticket or an explicit user request.
- Anything taken from Ali's original tree at `06890f6` or earlier is ported by hand and logged in `docs/ali_branch_merge.md`, never merged with git: that history is unrelated to this branch (decisions 15 and 24).
  Commits that port his work credit him with `Co-authored-by: ali-margem <ali.m.margem@gmail.com>`.
- No LLM in any path that sets an offer, a price or a credit limit; the chatbot and copilot only read (decision 17).

## Writing style

- Markdown: one full sentence per line.
- Never use the em dash character; use a plain dash.
- Commit messages: no AI co-author lines.

## Working on code

- Install [uv](https://docs.astral.sh/uv/), then from this folder: `uv sync`.
- `uv run churn --help` lists the pipeline commands.
- Before calling a ticket done: `uv run ruff check`, `uv run ruff format --check`, `uv run pytest`.
- Code in `src/prepaid_churn/` as pure, testable functions; the CLI in `cli.py` stays thin.
- Tests use the hand-made frame in `tests/conftest.py` or new small frames, never the real dataset.

## Map

| Path | What |
|---|---|
| `src/prepaid_churn/data.py` | Paths, loading, monthly column naming (`split_month`, `monthly_columns`) |
| `src/prepaid_churn/labels.py` | Inactivity rules (usage-based label, recharge-based check) |
| `src/prepaid_churn/profile.py` | T1 profiling functions and report |
| `src/prepaid_churn/schema.py` | T2 input data contract (`GROUPS` is the single source of truth), `validate` |
| `src/prepaid_churn/clean.py` | T3 cleaning rules (`clean`) |
| `src/prepaid_churn/windows.py` | T4 windows, labels, eligibility, customer split (`build_datasets`) |
| `src/prepaid_churn/features.py` | T5 engineered features (`FEATURES`, `add_features`) |
| `src/prepaid_churn/training.py` | T6 models, training and metrics |
| `src/prepaid_churn/evaluation.py` | T7 calibration, frozen `Champion`, test report |
| `src/prepaid_churn/bundle.py` | T8 model bundle: build, save, load with version and smoke checks |
| `src/prepaid_churn/scoring.py` | T8 `score`, plain-language reasons, output contract (`OUTPUT_COLUMNS`) |
| `src/prepaid_churn/value.py` | T10 training-frozen tiers, versioned artifact, 12-month revenue scenarios and output extension |
| `src/prepaid_churn/segmentation.py` | T10 training-only K-Means comparison, sampled Ward dendrogram, PCA plots and report |
| `src/prepaid_churn/retention.py` | T11 catalogue bonuses, policy assumptions, guardrails, holdout and equal-spend comparison |
| `src/prepaid_churn/campaign.py` | T11 authoritative proposal snapshots, named reviews and approved-only release |
| `src/prepaid_churn/retention_report.py` | T11 aggregate report with every cost and effect assumption |
| `src/prepaid_churn/almadar.py` | T16 Almadar catalogue and market facts (loading, rules, check against the operator file); T18 `almadar_view` |
| `src/prepaid_churn/service.py` | T15 read-only integration state and its payload builders (`load_state`, `health`, `catalogue`, `retention`, `portfolio_summary`, and `subscriber` from T20) |
| `src/prepaid_churn/api.py` | T15 FastAPI app, per-consumer API keys and the response models that generate `/docs` |
| `src/prepaid_churn/privacy.py` | T15 pseudonymous IDs: the Libyan phone-number check and the salted `pseudonymize` helper |
| `src/prepaid_churn/client.py` | T20 example client for the other components, standard library only, and the `check` behind `churn check-integration` |
| `src/prepaid_churn/demo.py` | T14 pure layer behind the demo screens: loading, headline numbers, guardrail breakdown, SMS parts and the customer message |
| `app/` | T14 Streamlit screens (`Home.py` plus `pages/`); thin, and the only write is a named review |
| `src/prepaid_churn/advance.py` | T19 emergency credit advice: affordability ceiling, operator denominations, zero-residual finding and report |
| `src/prepaid_churn/sequence.py` | T12 Keras LSTM over the two monthly steps, calibrated and scored against the champion on the frozen test (experiments group) |
| `data/processed/` | Built by `churn build-dataset` (git-ignored) |
| `artifacts/models/` | Built by `churn train` (git-ignored) |
| `artifacts/bundle/` | Built by `churn bundle` from a champion that passed its release gate (git-ignored) |
| `artifacts/scores/` | `scores.csv` from `churn score` and `almadar_view.csv` from `churn almadar-view` (git-ignored) |
| `artifacts/campaigns/` | T11 proposal snapshots, decision CSVs, review logs and approved-only release files (git-ignored) |
| `docs/data_contract.md` | Input contract, generated by `churn contract`; never edit by hand |
| `docs/output_contract.md` | Subscriber output contract, generated by `churn output-contract`; never edit by hand |
| `docs/model_card.md` | T9 model card: intended and out-of-scope use, data, metrics, limits; every figure names its report |
| `docs/integration.md` | T20 guide for the chatbot, copilot, network ML and antenna owners: endpoints, grounding rules, what to index, what we need from them |
| `docs/decisions.md` | Why every decision was made |
| `docs/ali_branch_merge.md` | Step log and port table for combining `Ali_Branch` into this module |
| `src/prepaid_churn/cli.py` | `churn` command |
| `reports/` | Generated reports with aggregate numbers (committed) |
| `data/raw/` | `train.csv`, `test.csv`, `data_dictionary.csv` from Kaggle (committed) |
| `data/almadar/` | Almadar packages (`offers.csv`), market facts (`market.toml`) and the operator source files; see `docs/almadar.md` |

## End of every session

1. Update the Handoff section at the top of TICKETS.md: status, blockers, next steps, open questions, date.
2. Update each touched ticket's Owner, Status and Findings.
3. Add any new decision, with its reason, to docs/decisions.md.
4. Run lint, format check and tests, and say in the handoff if anything is red.
