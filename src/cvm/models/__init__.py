"""Layer 4 -- the model layer.

    m1_churn    Silent churn: gradient-boosting benchmark, plus Cox survival
    m2_value    RFM-LE clustering, PCA, BG/NBD + Gamma-Gamma CLV
    m3_uplift   Treatment effect -- who can actually be influenced
    m4_advance  Repayment PD heads (share M1's feature pipeline)

The pipeline these serve:

    M1 predict churn -> M2 understand value -> M3 estimate treatment effect
      -> cvm.decision decides whether to intervene, and with what

Every experiment is logged to MLflow with params, metrics and artefacts. An
untracked run did not happen.
"""
