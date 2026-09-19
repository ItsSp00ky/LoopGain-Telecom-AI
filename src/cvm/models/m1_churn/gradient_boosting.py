"""Arm A -- LightGBM on engineered features.

Primary: LightGBM. Challengers: XGBoost, CatBoost.
Interpretable baselines: Decision Tree, Logistic Regression. Additional
baselines: Naive Bayes, KNN, SVM. All of these are REPORTED in the benchmark
table rather than discarded -- a boosted model that only narrowly beats
logistic regression is a useful thing to know before you ship the complex one.

Tuning: Optuna, time-boxed to 50 trials.

TWO FAMILIES, TWO TREATMENTS, AND THAT IS THE FAIR COMPARISON. The boosted
models take the matrix with its missing values intact, because handling them
natively is one of the things they are for. The classical baselines cannot,
so they get median imputation and scaling inside a pipeline. Giving every
model the same pre-processing would not be fairer -- it would mean either
crippling the boosted models or handing the baselines an imputation they were
never designed to need. Each gets its idiomatic best, and the table says so.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from cvm.config import load_conf, settings

log = logging.getLogger(__name__)

# Never features. The identifier identifies, the date leaks the split, the cell
# string is a concatenation of R/F/M/L/E which are already five columns of
# their own, and the target is the answer.
NOT_FEATURES = ("subscriber_id_hashed", "snapshot_date", "rfmle_cell")
CATEGORICAL = ("segment",)


def _conf() -> dict:
    return load_conf("models/m1_churn")["gradient_boosting"]


def prepare_matrix(
    df: pd.DataFrame, target: str | None = None, columns: list[str] | None = None
) -> tuple[pd.DataFrame, pd.Series | None]:
    """Split a feature-store frame into a numeric X and a y.

    ``columns`` pins the output to a known column list, which is what the
    serving path passes. Without it a subscriber whose segment happens to be
    absent from one batch would produce a matrix one column narrower than the
    model was trained on, and the model would either fail or -- worse -- score
    against misaligned columns.
    """
    target = load_conf("features")["target"]["name"] if target is None else target

    y = df[target].astype("int8") if target in df.columns else None
    X = df.drop(columns=[c for c in (*NOT_FEATURES, target) if c in df.columns])

    present = [c for c in CATEGORICAL if c in X.columns]
    if present:
        X = pd.get_dummies(X, columns=present, prefix=present, dtype="float64")

    # Everything else must already be numeric. A string column reaching a model
    # is a bug in the feature layer, and silently coercing it would hide that.
    non_numeric = [c for c in X.columns if not pd.api.types.is_numeric_dtype(X[c])]
    if non_numeric:
        raise TypeError(
            f"{non_numeric} are not numeric and are not declared categorical. Add them "
            "to CATEGORICAL or to NOT_FEATURES -- do not coerce them here."
        )

    if columns is not None:
        X = X.reindex(columns=columns, fill_value=0.0)
    else:
        X = _drop_duplicate_columns(X)

    return X.astype("float64"), y


def _drop_duplicate_columns(X: pd.DataFrame) -> pd.DataFrame:
    """Remove columns that are EXACTLY equal to an earlier one.

    The feature store legitimately holds two of these, and both are meaningful
    where they live:

      * `recency_raw` is the R input to RFM-LE and is by construction the same
        number as the velocity family's `days_since_last_topup`.
      * `at_recharge_floor` and `data_advance_leaves_nothing` coincide because
        the data advance and the smallest card are BOTH 5 LYD -- which is the
        M4 finding itself, showing up as two names for one condition.

    Two names for one signal is fine in a feature store and wrong in a design
    matrix. It halves each one's apparent SHAP importance, and it puts the same
    sentence into a five-item waterfall twice -- "has not topped up in 3 days",
    printed once for each column, which is 40% of a subscriber's explanation
    spent saying one thing.

    Dropped HERE and not in the feature layer so the store keeps its semantics,
    and logged rather than done quietly: if the ladder changes and the advance
    stops matching the smallest card, these stop being duplicates and the log
    line disappears, which is information.

    EQUALITY IS NOT THE ONLY WAY TO BE THE SAME COLUMN. Two more pairs survived
    the first version of this function because they are affine transforms
    rather than copies:

        offnet_share_30d      == 1 - onnet_ratio
        balance_zero_share_30d == balance_zero_hours_30d / 720

    Both carry |r| = 1.0, which matters more here than it would elsewhere,
    because the model that WINS this benchmark is logistic regression and
    perfectly collinear columns leave its coefficients unidentifiable -- they
    are pinned only by the L2 penalty, so the split between the pair is an
    artefact of regularisation strength rather than a fact about subscribers.
    It also put "spent 91 hours at zero balance" and "spent 13% of the month
    unable to transact" into the same five-item waterfall, which are one fact
    and two sentences.
    """
    duplicated = X.columns[X.T.duplicated()].tolist()
    kept = X.drop(columns=duplicated)

    # Then the affine ones. Correlation catches any a*x + b relationship, which
    # equality does not; the LATER column of each pair goes, so the choice is
    # deterministic rather than dependent on how the families happened to join.
    correlation = kept.corr().abs()
    collinear: list[str] = []
    for position, column in enumerate(kept.columns):
        earlier = kept.columns[:position].drop(collinear, errors="ignore")
        if len(earlier) and (correlation.loc[column, earlier] > 1 - 1e-9).any():
            partner = earlier[correlation.loc[column, earlier].argmax()]
            collinear.append(column)
            log.info("  %s is perfectly collinear with %s", column, partner)

    if duplicated or collinear:
        log.info(
            "dropped %d duplicated and %d perfectly-collinear column(s): %s",
            len(duplicated),
            len(collinear),
            duplicated + collinear,
        )
    return kept.drop(columns=collinear)


def _scale_pos_weight(y: pd.Series) -> float:
    """Negatives over positives. At a 3.5% base rate this is about 27."""
    positives = int(y.sum())
    if positives == 0:
        raise ValueError("no positive cases; the split cannot be trained on")
    return float((len(y) - positives) / positives)


def train(X: pd.DataFrame, y: pd.Series, X_val=None, y_val=None, kind: str = "lightgbm", **params):
    """Fit one boosted model. `kind` is lightgbm, xgboost or catboost.

    Early stopping needs a validation set that the model does not train on, so
    where one is supplied it is used and where it is not the configured
    `n_estimators` stands. Passing the TEST split here would be the classic
    way to leak: the stopping point is fitted to it, so the reported score is
    optimistic by exactly the amount the stopping bought.
    """
    conf = dict(_conf()["params"])
    rounds = conf.pop("early_stopping_rounds", 50)
    conf.pop("objective", None)
    conf.update(params)

    seed = settings.random_seed
    has_val = X_val is not None and y_val is not None

    if kind == "lightgbm":
        from lightgbm import LGBMClassifier, early_stopping, log_evaluation

        model = LGBMClassifier(
            objective="binary",
            # `metric` MUST be set, and it must be set here rather than only in
            # fit(). LightGBM otherwise tracks binary_logloss alongside whatever
            # eval_metric asks for, and early stopping watches EVERY tracked
            # metric. scale_pos_weight is about 27 at this base rate, which is
            # correct for ranking and deliberately wrecks the absolute
            # probability scale -- so logloss degrades from the first iteration
            # and stopping fires immediately. Measured: one tree instead of 97,
            # and PR-AUC 0.3076 instead of 0.4556. The model looked merely
            # mediocre rather than broken, which is why it survived a whole run.
            metric="average_precision",
            scale_pos_weight=_scale_pos_weight(y),
            random_state=seed,
            n_jobs=-1,
            verbose=-1,
            **conf,
        )
        fit_kwargs = {}
        if has_val:
            fit_kwargs = {
                "eval_set": [(X_val, y_val)],
                "eval_metric": "average_precision",
                "callbacks": [
                    early_stopping(rounds, verbose=False, first_metric_only=True),
                    log_evaluation(0),
                ],
            }
        model.fit(X, y, **fit_kwargs)
        if has_val and model.booster_.num_trees() <= 2:
            raise RuntimeError(
                f"lightgbm stopped after {model.booster_.num_trees()} tree(s). Early "
                "stopping is watching a metric that the class weighting degrades; check "
                "that `metric` is set on the constructor, not only eval_metric on fit()."
            )

    elif kind == "xgboost":
        from xgboost import XGBClassifier

        model = XGBClassifier(
            objective="binary:logistic",
            eval_metric="aucpr",
            scale_pos_weight=_scale_pos_weight(y),
            random_state=seed,
            n_jobs=-1,
            early_stopping_rounds=rounds if has_val else None,
            **{k: v for k, v in conf.items() if k != "min_child_samples"},
        )
        model.fit(X, y, eval_set=[(X_val, y_val)] if has_val else None, verbose=False)

    elif kind == "catboost":
        from catboost import CatBoostClassifier

        model = CatBoostClassifier(
            loss_function="Logloss",
            eval_metric="PRAUC",
            scale_pos_weight=_scale_pos_weight(y),
            random_seed=seed,
            verbose=0,
            allow_writing_files=False,
            iterations=conf.get("n_estimators", 1000),
            learning_rate=conf.get("learning_rate", 0.05),
            early_stopping_rounds=rounds if has_val else None,
        )
        model.fit(X, y, eval_set=(X_val, y_val) if has_val else None)

    else:
        raise ValueError(f"unknown model kind {kind!r}; expected lightgbm, xgboost or catboost")

    log.info("trained %s on %d x %d, %d positives", kind, *X.shape, int(y.sum()))
    return model


def tune(X: pd.DataFrame, y: pd.Series, n_trials: int | None = None, timeout: int | None = None):
    """Optuna search maximising average precision over temporal CV folds.

    TIME-BOXED MEANS TIME-BOXED. `n_trials` is the ceiling and `timeout` is the
    wall; whichever is reached first ends the search. A tuning step with no
    wall is a tuning step that decides for itself how long the build takes.

    Folds are EXPANDING AND TEMPORAL, taken from features/splits.py. K-fold
    here would validate on rows contemporaneous with training ones, which
    inflates every trial's score and picks hyperparameters tuned to a leak.
    """
    import optuna
    from sklearn.metrics import average_precision_score

    from cvm.features.splits import temporal_cv_folds

    tuning = _conf()["tuning"]
    n_trials = tuning["n_trials"] if n_trials is None else n_trials
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    # The index carries the time order out of the feature store; the folds need
    # a snapshot column, so it is rebuilt here rather than threaded through.
    if "snapshot_date" not in X.columns:
        ordered = pd.DataFrame({"snapshot_date": np.arange(len(X))}, index=X.index)
    else:
        ordered = X[["snapshot_date"]]
    folds = temporal_cv_folds(ordered, n_folds=3)

    def objective(trial: optuna.Trial) -> float:
        params = {
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.2, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 15, 127),
            "min_child_samples": trial.suggest_int("min_child_samples", 20, 200),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 100, 600),
        }
        scores = []
        for train_idx, validate_idx in folds:
            model = train(X.loc[train_idx], y.loc[train_idx], kind="lightgbm", **params)
            probability = model.predict_proba(X.loc[validate_idx])[:, 1]
            scores.append(average_precision_score(y.loc[validate_idx], probability))
        return float(np.mean(scores))

    study = optuna.create_study(
        direction=tuning["direction"],
        sampler=optuna.samplers.TPESampler(seed=settings.random_seed),
    )
    study.optimize(objective, n_trials=n_trials, timeout=timeout, show_progress_bar=False)

    log.info(
        "optuna: %d trials, best average precision %.4f, params %s",
        len(study.trials),
        study.best_value,
        study.best_params,
    )
    return study.best_params, study


def train_baselines(X: pd.DataFrame, y: pd.Series) -> dict:
    """Decision Tree, Logistic Regression, Naive Bayes, KNN, SVM.

    Reported in one table beside the boosted arms. Cheap to run, and they set
    the floor the ensemble has to clear to justify itself.

    Each is wrapped in a pipeline with median imputation and scaling, because
    none of them tolerate a missing value and the feature store carries 3-6%
    on most columns. `class_weight="balanced"` wherever it is offered -- at a
    3.5% base rate an unweighted classical model predicts the majority class
    for everyone and scores 96.5% accuracy, which is exactly the number the
    benchmark refuses to headline.

    SVM IS FITTED ON A SUBSAMPLE, and the table says so. An RBF kernel is
    between quadratic and cubic in the number of rows; on 60,000 it does not
    finish in a sensible time, and a baseline that costs more than the model
    it is a baseline for has stopped being a baseline.
    """
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.naive_bayes import GaussianNB
    from sklearn.neighbors import KNeighborsClassifier
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from sklearn.svm import SVC
    from sklearn.tree import DecisionTreeClassifier

    seed = settings.random_seed
    svm_cap = 10_000

    def pipe(estimator):
        return Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
                ("model", estimator),
            ]
        )

    specs = {
        "decision_tree": pipe(
            DecisionTreeClassifier(
                max_depth=6, min_samples_leaf=50, class_weight="balanced", random_state=seed
            )
        ),
        "logistic_regression": pipe(
            LogisticRegression(max_iter=2000, class_weight="balanced", random_state=seed)
        ),
        "naive_bayes": pipe(GaussianNB()),
        "knn": pipe(KNeighborsClassifier(n_neighbors=25, n_jobs=-1)),
        "svm": pipe(
            SVC(kernel="rbf", class_weight="balanced", probability=True, random_state=seed)
        ),
    }

    models: dict[str, object] = {}
    for name, estimator in specs.items():
        X_fit, y_fit = X, y
        if name == "svm" and len(X) > svm_cap:
            from sklearn.model_selection import train_test_split

            X_fit, _, y_fit, _ = train_test_split(
                X, y, train_size=svm_cap, stratify=y, random_state=seed
            )
            log.info(
                "svm: subsampled to %d rows (stratified) -- RBF does not scale to %d",
                svm_cap,
                len(X),
            )

        estimator.fit(X_fit, y_fit)
        models[name] = estimator
        log.info("  baseline %-22s fitted on %d rows", name, len(X_fit))

    return models
