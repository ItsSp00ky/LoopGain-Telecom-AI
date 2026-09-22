# Models and data of the prepaid customer module

Only this module; the GIS, network ML, chatbot and copilot parts are not listed.
Last checked 2026-09-22.

## Models

| Model | What it does |
|---|---|
| LightGBM | Predicts churn. The deployed model. |
| Logistic Regression | Baseline to prove LightGBM is worth it. |
| Sigmoid calibration (Platt) | Turns scores into real probabilities. |
| K-Means | Checks the value tiers. |
| Ward clustering | Same check, as a dendrogram. |
| PCA | Two-dimensional plot of the segments. |
| Keras LSTM | Sequence experiment. Lost to LightGBM. |
| CTGAN | Generates synthetic customers. |
| Gaussian Copula | Simpler synthetic baseline. |
| Two-model uplift | Compares uplift targeting with risk targeting. |

Only the first three are deployed.
The rest are comparisons and experiments.

The retention decisions (T11) and the emergency credit advice (T19) use no model at all; both are rule-based.

## Datasets

| Dataset | What it does |
|---|---|
| upGrad Telecom Churn (`data/raw/train.csv`) | Trains and tests the churn model. |
| upGrad unlabelled set (`data/raw/test.csv`) | The live base that gets scored. |
| Almadar `offers.csv` | The packages offered to customers. |
| Almadar `market.toml` | Prices, recharge cards, emergency credit and the ARPU assumption. |
| Orange Belgium (OpenML 45580) | Uplift experiment. |
| Criteo Uplift v2.1 | Uplift experiment. |
| Synthetic copies | Output of CTGAN and Copula, for the T13 test. |

Only the first four belong to the product.
The last three exist for experiments and are never committed.

The full numbers are in [model_card.md](model_card.md) and in the reports under `reports/`.
