# Contributing

Six engineers, fifteen working days, one integration. The rules below exist so the
last week is integration rather than archaeology.

---

## Working agreement

- **Daily stand-up, 15 minutes.** What landed, what is blocked, what you need from whom.
- **Trunk-based development.** Short-lived branches off `main`, merged by PR, reviewed
  by one other engineer. No branch lives longer than two days.
- **Hard integration checkpoint at the end of each week.** See the sprint schedule in
  the proposal, §6.2.
- **Day-10 feature freeze is non-negotiable.** Anything not working by the end of Day 10
  is descoped, not rescued. The descoping ladder (§6.3) is agreed in advance so cutting
  scope is a decision rather than a panic.

---

## Branches

```
<type>/<module>-<short-description>

feat/m1-calibration
feat/m3-offpeak-trough-detection
fix/m4-cooling-off-boundary
docs/model-card-m1
chore/ci-leakage-test
```

Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `data`.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/), with the module as scope:

```
feat(m1): isotonic calibration on the LightGBM arm
fix(m3): margin floor was applied before the loyalty bonus, not after
test(guardrails): assert cumulative discount never exceeds 15% of CLV
docs(m4): model card for the repayment PD head
```

## Pull requests

Fill in [the template](.github/PULL_REQUEST_TEMPLATE.md). A PR is reviewable when:

- CI is green — lint, tests, schema checks, and the leakage check.
- Guardrail and leakage tests were **run, not skipped**. If you touched
  `src/cvm/decision/`, add or update a test in `tests/guardrails/`.
- No data, model artefact, `.env`, or notebook output is in the diff.
- If it adds a generated field, `docs/data_dictionary.md` is updated in the same PR.
- If it changes a metric that appears in the report, the number in the report is updated too.

---

## Definition of Done

Copied from Appendix C of the proposal. A module is complete only when it:

1. has unit tests in CI;
2. is reachable through the API;
3. is visible in the UI;
4. is logged in MLflow with metrics;
5. has a model card or data-dictionary entry;
6. survives `docker compose up` from a clean clone **on a machine that is not the author's**.

Point 7 is the one that catches people. Test it on a teammate's laptop before you claim done.

---

## Code standards

```powershell
pwsh tasks.ps1 lint     # ruff check + black --check
pwsh tasks.ps1 fmt      # ruff --fix + black
pwsh tasks.ps1 test     # pytest
```

Install the hooks once and most of this happens automatically:

```bash
pre-commit install
```

- **Type hints on every public function.** Not enforced by CI, expected in review.
- **Config goes in `conf/*.yaml`, never hard-coded.** Every guardrail threshold,
  tier boundary and weight must be changeable without touching Python. An evaluator
  will ask to change one live.
- **Every stochastic step reads `CVM_RANDOM_SEED`.** Reproducibility is a deliverable.
- **Notebooks are for exploration.** Anything another module imports lives in `src/cvm/`.
  `nbstripout` clears outputs on commit — never commit subscriber-level output.

---

## Things that will get a PR rejected

These are not style opinions. They are the project's stated commitments.

| Rejected | Why |
|---|---|
| A raw MSISDN or any un-hashed identifier | §6.5. Hash at ingestion, SHA-256 + salt. |
| A random train/test split | Temporal splits only. Random splits leak the future. |
| Reporting accuracy as a headline metric | Meaningless at a 10–30% base rate. Use PR-AUC, lift, Brier. |
| A feature computed over a window that overlaps the label window | Point-in-time correctness. `tests/leakage/` should have caught it. |
| A field used to generate the synthetic label, used as a model feature | Same. This includes UCI `Customer Value`. |
| An LLM call anywhere in a pricing or credit decision path | §3.2 M7. The LLM reads and explains; it never decides. |
| A pricing or advance decision that does not write to `decision_log` | Auditability. Every decision must be replayable. |
| A guardrail weakened to make a demo look better | Guardrails are the ethical core. Change the demo. |
| A hard-coded secret or API key | Use `.env`. It is gitignored for a reason. |

---

## Reporting results honestly

The project's fourth pitch point is intellectual honesty, which means it has to be
true in the code as well as the slides:

- Report the **naive** number and the **honest** number side by side, with the gap explained.
- State plainly, in every artefact, that generated-data metrics are not evidence of
  production performance.
- If a classical baseline beats LightGBM, that is the result. Write it up. The benchmark is the
  deliverable, not the winner.
- If a module is descoped, say so in the report. Do not quietly drop it.

---

## Getting help

- Environment problems: [docs/setup.md](docs/setup.md)
- Architecture questions: [docs/architecture.md](docs/architecture.md)
- What a field means: [docs/data_dictionary.md](docs/data_dictionary.md)
- Why a decision was made: [docs/adr/](docs/adr/)
- Anything else: the module owner in the table in [README.md](README.md).
