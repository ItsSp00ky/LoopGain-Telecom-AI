"""Layer 4 -- M1 churn: the matrix, calibration, the benchmark, explanations.

Most of these guard things that fail QUIETLY. A model that early-stops after
one tree still returns probabilities. An uncalibrated score still ranks. A
plain-language explanation still renders if it says `shap = +0.14`. None of
them raise, and all of them are wrong.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cvm.models.m1_churn import benchmark, calibration, explain, gradient_boosting, survival


@pytest.fixture
def matrix() -> tuple[pd.DataFrame, pd.Series]:
    """A separable, imbalanced problem with the shape of the real one."""
    rng = np.random.default_rng(606)
    n = 4000
    signal = rng.normal(size=n)
    y = pd.Series((rng.random(n) < 1 / (1 + np.exp(-(signal * 1.5 - 3.2)))).astype("int8"))
    X = pd.DataFrame(
        {
            "days_since_last_topup": signal * 8 + 20,
            "recharge_count_90d": rng.integers(0, 30, n).astype("float64"),
            "leakage_score": rng.random(n),
            "noise": rng.normal(size=n),
        }
    )
    return X, y


@pytest.fixture
def frame(matrix) -> pd.DataFrame:
    """The same thing as a feature-store frame, with the columns to be dropped."""
    X, y = matrix
    return X.assign(
        subscriber_id_hashed=[f"{i:064x}" for i in range(len(X))],
        snapshot_date=pd.Timestamp("2026-01-01") + pd.to_timedelta(np.arange(len(X)) % 200, "D"),
        rfmle_cell="54321",
        segment=np.resize(["Champions", "Lost", "Hibernating"], len(X)),
        silent_churn_30d=y.values,
    )


# --- The matrix ------------------------------------------------------------


def test_identifier_date_and_cell_never_reach_a_model(frame):
    X, y = gradient_boosting.prepare_matrix(frame)
    for column in ("subscriber_id_hashed", "snapshot_date", "rfmle_cell", "silent_churn_30d"):
        assert column not in X.columns
    assert y is not None and y.sum() > 0


def test_segment_is_one_hot_and_everything_is_numeric(frame):
    X, _ = gradient_boosting.prepare_matrix(frame)
    assert "segment" not in X.columns
    assert len([c for c in X.columns if c.startswith("segment_")]) == 3
    assert all(pd.api.types.is_numeric_dtype(X[c]) for c in X.columns)


def test_a_batch_missing_a_segment_still_aligns(frame):
    """Serving must produce the training matrix's columns whatever is in the
    batch. A narrower matrix scores against misaligned columns."""
    full, _ = gradient_boosting.prepare_matrix(frame)
    one_segment = frame[frame["segment"] == "Lost"]

    served, _ = gradient_boosting.prepare_matrix(one_segment, columns=list(full.columns))

    assert list(served.columns) == list(full.columns)
    assert served["segment_Champions"].eq(0).all()


def test_an_undeclared_string_column_is_refused(frame):
    """Silently coercing it would hide a bug in the feature layer."""
    with pytest.raises(TypeError, match="not numeric"):
        gradient_boosting.prepare_matrix(frame.assign(some_new_string="x"))


def test_an_exactly_duplicated_column_is_dropped(frame):
    """The store holds two real duplicate pairs: `recency_raw` IS
    `days_since_last_topup`, and `at_recharge_floor` IS
    `data_advance_leaves_nothing` because the advance and the smallest card are
    both 5 LYD. Two names for one signal halves each one's SHAP importance and
    prints the same sentence twice in a five-item waterfall."""
    doubled = frame.assign(recency_raw=frame["days_since_last_topup"])

    X, _ = gradient_boosting.prepare_matrix(doubled)

    assert "days_since_last_topup" in X.columns
    assert "recency_raw" not in X.columns, "the duplicate survived into the design matrix"


def test_a_perfectly_collinear_column_is_dropped(frame):
    """Equality is not the only way to be the same column. The store holds two
    affine pairs -- `offnet_share_30d == 1 - onnet_ratio` and
    `balance_zero_share_30d == balance_zero_hours_30d / 720` -- which survive an
    equality check and carry |r| = 1.0.

    It matters more than it would elsewhere because the model that WINS this
    benchmark is logistic regression, and perfectly collinear columns leave its
    coefficients pinned only by the L2 penalty."""
    affine = frame.assign(leakage_pct=frame["leakage_score"] * 100 - 7)

    X, _ = gradient_boosting.prepare_matrix(affine)

    assert "leakage_score" in X.columns
    assert "leakage_pct" not in X.columns, "an affine duplicate survived"


def test_a_merely_correlated_column_survives(frame):
    """The guard must not eat genuinely distinct features. Two columns can be
    strongly related and still each carry signal the other does not."""
    rng = np.random.default_rng(0)
    noisy = frame.assign(leakage_echo=frame["leakage_score"] * 2 + rng.normal(0, 0.05, len(frame)))
    X, _ = gradient_boosting.prepare_matrix(noisy)
    assert "leakage_echo" in X.columns, "a correlated-but-distinct column was dropped"


def test_serving_keeps_the_training_columns_verbatim(frame):
    """Dedup runs when the column list is being DISCOVERED, not when it is
    given. A serving batch must produce exactly the training columns, and
    silently dropping one because this particular batch happened to make two
    columns equal would misalign the matrix."""
    doubled = frame.assign(recency_raw=frame["days_since_last_topup"])
    training, _ = gradient_boosting.prepare_matrix(doubled)

    # A batch where two OTHER columns happen to coincide.
    odd = doubled.assign(leakage_score=doubled["noise"])
    served, _ = gradient_boosting.prepare_matrix(odd, columns=list(training.columns))

    assert list(served.columns) == list(training.columns)


def test_scale_pos_weight_matches_the_imbalance(matrix):
    _, y = matrix
    weight = gradient_boosting._scale_pos_weight(y)
    assert weight == pytest.approx((len(y) - y.sum()) / y.sum())
    assert weight > 5, "the fixture is supposed to be imbalanced"


# --- The bug that cost the most --------------------------------------------


def test_lightgbm_does_not_stop_after_one_tree(matrix):
    """REGRESSION. LightGBM tracks binary_logloss alongside whatever eval_metric
    asks for, and early stopping watches every tracked metric. scale_pos_weight
    is ~27 here, which is right for ranking and deliberately wrecks the absolute
    probability scale -- so logloss degrades from iteration 1 and stopping fires
    immediately. Measured on the real population: 1 tree instead of 97, PR-AUC
    0.3076 instead of 0.4556. It looked mediocre, not broken."""
    X, y = matrix
    cut = int(len(X) * 0.7)
    model = gradient_boosting.train(
        X.iloc[:cut], y.iloc[:cut], X.iloc[cut:], y.iloc[cut:], kind="lightgbm", n_estimators=200
    )
    assert model.booster_.num_trees() > 10, "early stopping is watching the wrong metric again"


# --- Calibration -----------------------------------------------------------


def test_calibration_cannot_reorder_anyone(matrix):
    """Isotonic is monotone NON-DECREASING, which is the exact property: nobody
    who scored above someone else ends up below them.

    Tested directly on the order rather than through AUC, because AUC is the
    weaker check -- isotonic maps distinct scores onto shared values, and those
    new ties shift a rank metric slightly even though nothing was reordered.
    Asserting the AUCs are identical fails for a reason that is not a bug."""
    from sklearn.metrics import average_precision_score

    X, y = matrix
    cut = int(len(X) * 0.6)
    model = gradient_boosting.train(X.iloc[:cut], y.iloc[:cut], kind="lightgbm", n_estimators=60)
    wrapped = calibration.calibrate(model, X.iloc[cut:], y.iloc[cut:])

    raw = calibration._raw_probability(model, X.iloc[cut:])
    cooked = wrapped.predict_proba(X.iloc[cut:])[:, 1]

    # The real property: sort by raw, and the calibrated scores never go down.
    ordered = cooked[np.argsort(raw, kind="stable")]
    assert (np.diff(ordered) >= -1e-12).all(), "isotonic reordered two subscribers"

    # Ties are allowed, and they are the only reason AUC moves at all.
    assert len(np.unique(cooked)) <= len(np.unique(raw))
    assert average_precision_score(y.iloc[cut:], raw) == pytest.approx(
        average_precision_score(y.iloc[cut:], cooked), abs=0.01
    )


def test_calibration_moves_the_mean_onto_the_base_rate(matrix):
    """The whole point. scale_pos_weight inflates the scores; a calibrated mean
    that does not land near the observed rate means it did not work."""
    X, y = matrix
    cut = int(len(X) * 0.6)
    model = gradient_boosting.train(X.iloc[:cut], y.iloc[:cut], kind="lightgbm", n_estimators=60)
    wrapped = calibration.calibrate(model, X.iloc[cut:], y.iloc[cut:])

    raw = calibration._raw_probability(model, X.iloc[cut:]).mean()
    cooked = wrapped.predict_proba(X.iloc[cut:])[:, 1].mean()
    observed = y.iloc[cut:].mean()

    assert abs(cooked - observed) < abs(raw - observed)
    assert cooked == pytest.approx(observed, abs=0.02)


def test_a_calibration_slice_with_no_positives_is_refused(matrix):
    """An isotonic map fitted on three positives is noise applied to every score."""
    X, y = matrix
    model = gradient_boosting.train(X, y, kind="lightgbm", n_estimators=20)
    with pytest.raises(ValueError, match="positive case"):
        calibration.calibrate(model, X.head(50), pd.Series(np.zeros(50, dtype=int)))


def test_brier_rewards_honesty():
    """A proper scoring rule: the true rate beats both timid and bold."""
    y = np.array([1, 0, 0, 0])
    assert calibration.brier_score(y, np.full(4, 0.25)) < calibration.brier_score(
        y, np.full(4, 0.6)
    )
    assert calibration.brier_score(y, np.full(4, 0.25)) < calibration.brier_score(
        y, np.full(4, 0.02)
    )
    assert calibration.brier_score(y, y.astype(float)) == 0.0


def test_reliability_bins_by_quantile_not_width():
    """At a 3.5% base rate equal-width bins put everyone in the first one, which
    looks like perfect calibration and is no information at all."""
    rng = np.random.default_rng(0)
    p = rng.beta(1, 30, 5000)
    y = (rng.random(5000) < p).astype(int)

    curve = calibration.calibration_curve_data(y, p, n_bins=10)

    assert len(curve) >= 8, "the bins collapsed; this is the equal-width failure"
    assert curve["count"].std() / curve["count"].mean() < 0.1, "bins are not equal-sized"


# --- The benchmark ---------------------------------------------------------


def test_lift_is_one_for_a_random_ranker():
    rng = np.random.default_rng(1)
    y = (rng.random(10000) < 0.05).astype(int)
    assert benchmark.lift_at_decile(y, rng.random(10000), 1) == pytest.approx(1.0, abs=0.35)


def test_lift_is_maximal_for_a_perfect_ranker():
    """A perfect ranker at a 5% base rate puts every churner in the top decile,
    so lift is capped by the base rate at 1/0.05 = 20 -- but only 10% of the
    population fits, so it reaches min(10, 1/base)."""
    y = np.concatenate([np.ones(500), np.zeros(9500)]).astype(int)
    assert benchmark.lift_at_decile(y, y.astype(float), 1) == pytest.approx(10.0, abs=0.1)
    assert benchmark.recall_at_decile(y, y.astype(float), 1) == pytest.approx(1.0)


def test_accuracy_never_leads_the_table(matrix):
    """The reporting rule, enforced rather than trusted to a reviewer."""
    X, y = matrix
    cut = int(len(X) * 0.7)
    models = {
        "lightgbm": gradient_boosting.train(
            X.iloc[:cut], y.iloc[:cut], kind="lightgbm", n_estimators=40
        )
    }
    table = benchmark.run_benchmark(models, X.iloc[cut:], y.iloc[cut:])

    assert table.columns[1] == "pr_auc"
    assert table.columns[-1] == "accuracy"


def test_the_verdict_names_the_linear_generator(matrix):
    """The caveat that matters more than the ranking. The synthetic label comes
    from a logistic hazard, so logistic regression is correctly specified and
    the benchmark is partly measuring the generator, not the models."""
    table = pd.DataFrame(
        {
            "model": ["logistic_regression", "lightgbm"],
            "pr_auc": [0.4711, 0.4434],
            "lift_at_decile_1": [6.33, 6.26],
            "recall_at_decile_1": [0.63, 0.62],
            "base_rate": [0.0319, 0.0319],
        }
    )
    verdict = benchmark.architecture_verdict(table)

    assert "generator is linear" in verdict
    assert "NOT evidence" in verdict


def test_the_verdict_stays_quiet_when_a_tree_clearly_wins():
    """The caveat is specific to a linear model placing at the top. Emitting it
    unconditionally would make it wallpaper."""
    table = pd.DataFrame(
        {
            "model": ["lightgbm", "catboost", "logistic_regression"],
            "pr_auc": [0.72, 0.70, 0.41],
            "lift_at_decile_1": [8.1, 8.0, 5.2],
            "recall_at_decile_1": [0.81, 0.80, 0.52],
            "base_rate": [0.0319, 0.0319, 0.0319],
        }
    )
    verdict = benchmark.architecture_verdict(table)
    assert "generator is linear" not in verdict
    assert "earns its complexity" in verdict


# --- Explanations ----------------------------------------------------------


def test_plain_language_leaks_no_jargon():
    """A sentence containing the column name and the SHAP number has been
    annotated, not translated, and a marketing analyst still cannot act on it."""
    sentence = explain.to_plain_language("days_since_last_topup", 23.0, 0.14)

    assert "23" in sentence and "days" in sentence
    assert "days_since_last_topup" not in sentence
    assert "shap" not in sentence.lower() and "0.14" not in sentence


def test_every_served_column_has_real_phrasing():
    """The fallback exists so a NEW feature degrades to a sentence instead of a
    KeyError -- not so shipped features can lean on it. `engagement raw is 0.50`
    reached a Subscriber 360 screen before this test existed.

    Skips when the store is absent, because the column list is the point."""
    from cvm.config import settings
    from cvm.models.m1_churn.explain import PHRASING

    if not settings.feature_store_offline.exists():
        pytest.skip("feature store not built; run `python -m cvm.features.run`")

    served, _ = gradient_boosting.prepare_matrix(pd.read_parquet(settings.feature_store_offline))
    # One-hot segments render from the segment name itself, not a template.
    missing = [c for c in served.columns if c not in PHRASING and not c.startswith("segment_")]
    assert (
        not missing
    ), f"{len(missing)} served column(s) fall back to the generic phrasing: {missing}"


def test_an_unknown_feature_degrades_to_a_sentence():
    """A new feature must not take the serving path down with a KeyError."""
    sentence = explain.to_plain_language("some_new_metric_30d", 4.0, -0.02)
    assert "some_new_metric_30d" not in sentence
    assert "lowers churn risk" in sentence


def test_direction_is_reported_both_ways():
    assert "raises" in explain.to_plain_language("leakage_score", 0.8, +0.2)
    assert "lowers" in explain.to_plain_language("leakage_score", 0.1, -0.2)


def test_every_feature_lands_in_a_family(frame):
    X, _ = gradient_boosting.prepare_matrix(frame)
    families = {explain.family_of(c) for c in X.columns}
    assert "velocity" in families and "leakage" in families
    unmatched = [c for c in X.columns if explain.family_of(c) == "other"]
    assert unmatched == ["noise"], f"unexpectedly unfamilied: {unmatched}"


def test_shap_list_output_picks_the_positive_class():
    """LightGBM's TreeExplainer returns a LIST of two arrays, not a 3-D one.
    Indexing the wrong element explains the NEGATIVE class and every sign
    flips -- which raises nothing and reads as a plausible explanation."""
    negative = np.array([[1.0, 2.0]])
    positive = np.array([[-1.0, -2.0]])
    assert explain._positive_class([negative, positive]) is not None
    np.testing.assert_array_equal(explain._positive_class([negative, positive]), positive)
    np.testing.assert_array_equal(explain._positive_class(positive), positive)
    stacked = np.stack([negative, positive], axis=-1)
    np.testing.assert_array_equal(explain._positive_class(stacked), positive)


def test_linear_attribution_is_exact(matrix):
    """For a linear model the SHAP value IS coef * (x - E[x]), so the
    contributions must sum to the model's logit minus its mean logit."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    X, y = matrix
    pipeline = Pipeline([("scale", StandardScaler()), ("model", LogisticRegression(max_iter=500))])
    pipeline.fit(X, y)

    explainer = explain.LinearExplainer(pipeline, X)
    contributions = explainer.shap_values(X)

    logit = pipeline.decision_function(X)
    assert contributions.sum(axis=1) == pytest.approx(logit - logit.mean(), abs=1e-8)


def test_an_unexplainable_model_is_refused(matrix):
    """KNN and SVM are in the benchmark for comparison, not for serving. An
    unexplainable score cannot carry an offer."""
    X, y = matrix
    models = gradient_boosting.train_baselines(X.head(400), y.head(400))
    with pytest.raises(TypeError, match="neither a tree nor linear"):
        explain.explainer_for(models["knn"], X.head(50))


def test_family_shares_sum_to_one(matrix):
    X, y = matrix
    model = gradient_boosting.train(X, y, kind="lightgbm", n_estimators=40)
    explainer = explain.explainer_for(model, X)

    shares = explain.attribution_by_family(explainer, X.head(200))
    numeric = shares.drop(columns=["dominant_family"])

    assert numeric.sum(axis=1).to_numpy() == pytest.approx(1.0, abs=1e-9)
    assert (numeric >= 0).all().all(), "shares are over absolute contributions"


# --- Survival --------------------------------------------------------------


def test_survivors_are_censored_not_given_a_long_life(frame):
    """ "Left on day 120" and "had not left by day 134" are different
    observations. Treating the second as the first biases every estimate."""
    population = pd.DataFrame(
        {
            "subscriber_id_hashed": frame["subscriber_id_hashed"],
            "days_to_churn": np.where(frame["silent_churn_30d"] == 1, 120, -1),
            "silent_churn_30d": frame["silent_churn_30d"],
        }
    )
    built = survival.build_survival_frame(frame, population)

    censored = built[built[survival.EVENT] == 0][survival.DURATION]
    assert (censored == survival._horizon()).all()
    assert (built[survival.DURATION] > 0).all(), "a negative duration reached lifelines"


def test_a_label_artifact_cannot_ride_in_as_a_covariate(frame):
    """`hazard_score` is the outcome's generator. As a survival covariate it
    reconstructs the answer exactly."""
    population = pd.DataFrame(
        {
            "subscriber_id_hashed": frame["subscriber_id_hashed"],
            "days_to_churn": 120,
            "silent_churn_30d": frame["silent_churn_30d"],
        }
    )
    with pytest.raises(AssertionError, match="never as inputs"):
        survival.build_survival_frame(frame.assign(hazard_score=0.5), population)


def test_ladder_boundaries_are_refused_when_they_are_noise():
    """Uniform event days have no inflection, so the three "largest drops" are
    the three largest random fluctuations. Returning them as derived ladder
    boundaries is false precision.

    A chi-square was tried first and is the wrong test: at 3,523 events it
    rejects uniformity on trivial overdispersion (p=0.025) and then blesses
    boundaries that two halves of the same data disagree about."""
    rng = np.random.default_rng(606)
    uniform = rng.integers(105, 135, 3523)

    spread = survival._boundary_spread(uniform)
    assert spread > survival.MAX_BOUNDARY_SPREAD_DAYS, f"noise passed at spread {spread:.2f}"


def test_ladder_boundaries_are_returned_when_the_curve_has_shape():
    """The mirror image, and the one that makes the guard worth having. A guard
    that always refuses is not a guard, it is a broken function."""
    rng = np.random.default_rng(606)
    with_cliffs = np.concatenate([rng.integers(105, 135, 1500), np.repeat([110, 120, 130], 700)])

    spread = survival._boundary_spread(with_cliffs)
    assert spread <= survival.MAX_BOUNDARY_SPREAD_DAYS
    assert survival._largest_drops(with_cliffs) == [110, 120, 130]
