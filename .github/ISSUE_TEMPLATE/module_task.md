---
name: Module task
about: A unit of work on M1–M4 or Layers 1–8
title: "[M?] "
labels: task
assignees: ''
---

**Module:** <!-- M1 Churn / M2 Value / M3 Pricing / M4 Advance / Layer 1-3 / Infra / Integration -->
**Owner:** <!-- E1 … E6 -->
**Sprint day:** <!-- 1–15, from the schedule in the proposal §6.2 -->

## Goal

<!-- One sentence. What exists at the end that does not exist now. -->

## Acceptance criteria

- [ ]
- [ ]

## Definition of Done (Appendix C)

Tick only what applies at this stage; the full list must be green before the
module is called complete.

- [ ] Unit tests in CI
- [ ] Reachable through the API
- [ ] Visible in the UI
- [ ] Logged in MLflow with metrics
- [ ] Model card or data-dictionary entry
- [ ] Survives `docker compose up` from a clean clone on another machine

## Descoping

If this is at risk, what is the fallback? (See the descoping ladder, §6.3.)

<!-- e.g. "Falls back to a single global off-peak window instead of per-cell trough detection." -->
