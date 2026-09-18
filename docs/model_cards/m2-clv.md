# Model Card -- M2 - Customer Lifetime Value

> **Not written yet.** Copy [TEMPLATE.md](TEMPLATE.md) into this file and fill
> it in. A model card is item 5 of the Definition of Done -- the module is not
> finished without one.

| | |
|---|---|
| **Module** | M2 |
| **Owner** | E3 |
| **Code** | `src/cvm/models/m2_value/clv.py` |
| **Config** | `conf/models/m2_value.yaml` |
| **Version** | -- |
| **MLflow run** | -- |

## Notes for whoever writes this

BG/NBD + Gamma-Gamma, treating each recharge as a transaction. The non-contractual, alive-or-dead-unobserved assumption is literally true in prepaid. Benchmarked against the IBM CLTV field. CLV is the budget ceiling for all retention spend, so an over-optimistic CLV loosens every guardrail downstream - say so under Limitations.

Whatever else this card says, it must state that metrics are computed on
generated data and are not evidence of production performance.