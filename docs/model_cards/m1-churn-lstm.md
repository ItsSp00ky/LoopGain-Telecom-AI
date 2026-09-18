# Model Card -- M1 Arm B - Silent Churn (LSTM)

> **Not written yet.** Copy [TEMPLATE.md](TEMPLATE.md) into this file and fill
> it in. A model card is item 5 of the Definition of Done -- the module is not
> finished without one.

| | |
|---|---|
| **Module** | M1 |
| **Owner** | E2 |
| **Code** | `src/cvm/models/m1_churn/arm_b_lstm.py` |
| **Config** | `conf/models/m1_churn.yaml` |
| **Version** | -- |
| **MLflow run** | -- |

## Notes for whoever writes this

Benchmark arm on raw 90 x k daily sequences, no hand aggregation. The card must state the verdict either way: if LightGBM wins, explain why (sparse mostly-zero daily activity is a weak sequence signal; engineered decay ratios already encode most of the temporal information). The benchmark is the deliverable, not the winner. Trained on Colab T4.

Whatever else this card says, it must state that metrics are computed on
generated data and are not evidence of production performance.