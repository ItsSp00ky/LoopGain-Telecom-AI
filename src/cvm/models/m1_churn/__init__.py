"""M1 -- Silent Churn Engine.

Step one of the pipeline: who is leaving, and when?

Structured as a BENCHMARK rather than a single model -- LightGBM primary,
XGBoost and CatBoost as challengers, and Decision Tree, Logistic Regression,
Naive Bayes, KNN and SVM reported beside them rather than discarded. One
temporal split, one set of metrics, calibration curves for all of them.

    gradient_boosting.py   LightGBM + challengers
    benchmark.py           the comparison table (deliverable D3)
    calibration.py         isotonic; a 0.31 must mean 31%
    explain.py             exact SHAP, per subscriber
    survival.py            M1b -- Cox, answering *when* rather than *if*

TABULAR ON PURPOSE. A sequence arm over raw 90-day daily tensors was
considered and dropped: 90 timesteps of mostly-zero prepaid activity is a weak
sequence signal, the engineered decay ratios in features/velocity.py already
encode most of the temporal information, and it would have been the only part
of this component needing a GPU. Every model here is CPU-trainable and exactly
SHAP-explainable, which is what the decision engine downstream requires.
"""
