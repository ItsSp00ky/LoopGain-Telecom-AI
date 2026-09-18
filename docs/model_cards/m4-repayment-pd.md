# Model Card -- M4 - Advance Repayment PD

> **Not written yet.** Copy [TEMPLATE.md](TEMPLATE.md) into this file and fill
> it in. A model card is item 5 of the Definition of Done -- the module is not
> finished without one.

| | |
|---|---|
| **Module** | M4 |
| **Owner** | E2 |
| **Code** | `src/cvm/models/m4_advance/repayment_pd.py` |
| **Config** | `conf/advance.yaml` |
| **Version** | -- |
| **MLflow run** | -- |

## Notes for whoever writes this

Second prediction head sharing M1 features. Target: advance_repaid_within_7d. This card carries the heaviest ethics section in the project - the objective is line survival, not recovery yield. Must document: chronic-distress exclusion, cooling-off periods, CLV-bounded exposure, the line-reset risk flag, the fixed-fee structure flagged for Shariah review, and the reject-inference correction for selection bias.

Whatever else this card says, it must state that metrics are computed on
generated data and are not evidence of production performance.