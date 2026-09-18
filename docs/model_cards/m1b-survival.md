# Model Card -- M1b - Time-to-Churn (Cox PH)

> **Not written yet.** Copy [TEMPLATE.md](TEMPLATE.md) into this file and fill
> it in. A model card is item 5 of the Definition of Done -- the module is not
> finished without one.

| | |
|---|---|
| **Module** | M1b |
| **Owner** | E2 |
| **Code** | `src/cvm/models/m1_churn/survival.py` |
| **Config** | `conf/models/m1_churn.yaml` |
| **Version** | -- |
| **MLflow run** | -- |

## Notes for whoever writes this

Classification answers if; this answers when. Concordance index is the reported metric. The hazard inflection points define the retention ladder stage boundaries in conf/pricing.yaml, so a change here changes campaign timing - note that dependency in the card.

Whatever else this card says, it must state that metrics are computed on
generated data and are not evidence of production performance.