# Models and data of the prepaid customer module

Only this module; the GIS, network ML, chatbot and copilot parts are not listed.
Last checked 2026-09-26.

## Models

| Model | What it does |
|---|---|
| LightGBM | Predicts churn. The deployed model. |
| Logistic Regression | Baseline to prove LightGBM is worth it. |
| Sigmoid calibration (Platt) | Turns scores into real probabilities. |
| K-Means | Checks the value tiers. |
| Ward clustering | Same check, as a dendrogram. |
| PCA | Two-dimensional plot of the segments. |

Only the first three are deployed; the other three check the value tiers.
An LSTM and a model trained on synthetic customers were also tested; both were worse than LightGBM and were removed (model card, decision 44).

The retention decisions (T11) and the emergency credit advice (T19) use no model at all; both are rule-based.

## Datasets

| Dataset | What it does |
|---|---|
| upGrad Telecom Churn (`data/raw/train.csv`) | Trains and tests the churn model. |
| upGrad unlabelled set (`data/raw/test.csv`) | The live base that gets scored. |

Both belong to the product.

The full numbers are in [model_card.md](model_card.md) and in the reports under `reports/`.
