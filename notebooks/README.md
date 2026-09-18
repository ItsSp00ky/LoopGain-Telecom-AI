# Notebooks

**Exploration only.** Anything another module imports lives in `src/cvm/`.

A notebook is where you work out what the code should be. Once you know,
move it into the package and import it back into the notebook. Notebooks that
accumulate logic become a second, untested codebase that the API cannot reach.

```
00_eda/               Dataset exploration, dedup audit, leakage audit          E1
01_synthesis/         CTGAN vs TVAE vs Copula, SDMetrics gate tuning           E1
02_churn/             M1 tuning, benchmark table, calibration curves           E2
03_value/             M2 clustering, k selection, PCA, CLV benchmarking        E3
04_uplift_decision/   M3 uplift + Qini, decision engine, guardrail sensitivity E4
05_integration/       API contract checks, cohort query shaping                Ali
```

## Rules

- **Outputs are stripped on commit** by `nbstripout` (see
  `.pre-commit-config.yaml`). Never commit subscriber-level output -- even
  generated rows set a bad habit, and a reviewer cannot tell at a glance
  whether a given table is synthetic.
- **Name them `NN_short_description.ipynb`** so the execution order is obvious.
- **Seed everything** with `cvm.config.seed_everything()`. A notebook result
  nobody can reproduce is an anecdote.
- **Everything here runs on CPU.** No notebook in this component needs a GPU
  runtime; if one starts to, that is a scope question, not a hardware one.