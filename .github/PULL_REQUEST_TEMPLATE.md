## What

<!-- One or two sentences. What changed and why. -->

**Module:** <!-- M1 / M2 / M3 / M4 / Layer 1-3 / Infra / Integration / Docs -->
**Closes:** #

## How to verify

<!-- The exact commands a reviewer should run. -->

```
pwsh tasks.ps1 test
```

## Results

<!-- Delete if not a modelling change. Report the honest numbers. -->

| Metric | Before | After |
|---|---|---|
| PR-AUC | | |
| Lift @ decile 1 | | |
| Brier | | |

<!-- If a naive figure differs from the honest one, show both and explain the gap. -->

---

## Checklist

- [ ] CI is green, including the **leakage** and **guardrail** jobs
- [ ] Guardrail/leakage tests were run, not skipped or marked xfail
- [ ] New or changed behaviour has a test
- [ ] No data files, model artefacts, `.env`, or notebook outputs in the diff
- [ ] No raw MSISDN or un-hashed identifier anywhere
- [ ] Temporal split used (never random) if this touches training
- [ ] Accuracy is **not** reported as a headline metric
- [ ] Thresholds and weights live in `conf/*.yaml`, not hard-coded
- [ ] Stochastic steps read `CVM_RANDOM_SEED`

If this PR adds a generated field:
- [ ] `docs/data_dictionary.md` updated in this same PR

If this PR completes a module (Appendix C, Definition of Done):
- [ ] Unit tests in CI
- [ ] Reachable through the API
- [ ] Visible in the UI
- [ ] Logged in MLflow with metrics
- [ ] Model card written (`docs/model_cards/`)
- [ ] Survives `docker compose up` from a clean clone **on someone else's machine**
