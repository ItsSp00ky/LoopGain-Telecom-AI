# Model Card -- M1 Arm A - Silent Churn (LightGBM)

> **Not written yet.** Copy [TEMPLATE.md](TEMPLATE.md) into this file and fill
> it in. A model card is item 5 of the Definition of Done -- the module is not
> finished without one.

| | |
|---|---|
| **Module** | M1 |
| **Owner** | E2 |
| **Code** | `src/cvm/models/m1_churn/arm_a_lightgbm.py` |
| **Config** | `conf/models/m1_churn.yaml` |
| **Version** | -- |
| **MLflow run** | -- |

## Notes for whoever writes this

Primary churn model. Feeds the pricing engine, so isotonic calibration is mandatory - a 0.31 must mean 31%. Report PR-AUC, lift @ deciles 1-3 and Brier. Include the naive-vs-honest table: published work reaches ~97% accuracy and ~0.99 AUC on this data, inflated by ~300 duplicate rows and the leaky Customer Value field.

Whatever else this card says, it must state that metrics are computed on
generated data and are not evidence of production performance.