"""Layer 4 -- the model layer.

    m1_churn    Silent churn: LightGBM vs LSTM benchmark, plus Cox survival
    m2_value    RFM-LE clustering, PCA, BG/NBD + Gamma-Gamma CLV
    m4_advance  Repayment PD head (shares M1's feature pipeline)

Every experiment is logged to MLflow with params, metrics and artefacts. An
untracked run did not happen.
"""