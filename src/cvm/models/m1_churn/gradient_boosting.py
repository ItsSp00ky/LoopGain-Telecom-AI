"""Arm A -- LightGBM on engineered features.

Primary: LightGBM. Challengers: XGBoost, CatBoost.
Interpretable baselines: Decision Tree, Logistic Regression. Additional
baselines: Naive Bayes, KNN, SVM. All of these are REPORTED in the benchmark
table rather than discarded -- a boosted model that only narrowly beats
logistic regression is a useful thing to know before you ship the complex one.

Tuning: Optuna, time-boxed to 50 trials.
"""

from __future__ import annotations

import pandas as pd


def train(X: pd.DataFrame, y: pd.Series, **params):
    raise NotImplementedError("TODO(E2)")


def tune(X: pd.DataFrame, y: pd.Series, n_trials: int = 50):
    """Optuna search maximising average precision over temporal CV folds."""
    raise NotImplementedError("TODO(E2)")


def train_baselines(X: pd.DataFrame, y: pd.Series) -> dict:
    """Decision Tree, Logistic Regression, Naive Bayes, KNN, SVM.

    Reported in one table beside the boosted arms. Cheap to run, and they set
    the floor the ensemble has to clear to justify itself.
    """
    raise NotImplementedError("TODO(E2)")
