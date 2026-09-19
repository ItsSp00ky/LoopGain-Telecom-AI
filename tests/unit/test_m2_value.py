"""Layer 4 -- M2 value: the CLV summary, the fitters, and segment discovery.

The CLV number is not a reporting nicety. It becomes the RETENTION BUDGET
CEILING, so an overstated CLV authorises overspending on a subscriber who will
never earn it back, and nothing downstream would catch that -- the pricing
engine would be obeying its guardrail correctly against a wrong number.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cvm.config import load_conf
from cvm.models.m2_value import clv, segmentation


@pytest.fixture
def base() -> pd.DataFrame:
    """A recharge base with the shape of the real one, missingness included.

    Generated from a GENUINE BG/NBD process rather than independent draws, then
    inverted back into the population's column shape. The first version drew
    frequency and recency independently, which is not a purchase process at
    all -- frequent buyers bought recently, and a likelihood built on that
    structure has no maximum when the structure is absent. lifetimes raised
    ConvergenceError, which reads like a bug in the code under test and was a
    bug in the fixture.

    Parameters are the ones actually fitted on the real base (r=2.95,
    alpha=28.38, b=4.68), so the test data resembles the production data.
    """
    from lifetimes.generate_data import beta_geometric_nbd_model

    rng = np.random.default_rng(606)
    n = 3000
    process = beta_geometric_nbd_model(T=90, r=2.95, alpha=28.38, a=0.3, b=4.68, size=n)

    # Invert `summary_from_population`: it is the exact construction this
    # module performs, run backwards.
    frame = pd.DataFrame(
        {
            "subscriber_id_hashed": [f"{i:064x}" for i in range(n)],
            "recharge_count_90d": (process["frequency"] + 1).to_numpy(dtype="float64"),
            "days_since_last_topup": (process["T"] - process["recency"]).to_numpy(),
            "modal_recharge_amount_lyd": rng.choice([5.0, 10.0, 20.0, 40.0, 100.0], n),
            "tenure_months": process["T"].to_numpy() / 30.0,
            "R": rng.integers(1, 6, n),
            "F": rng.integers(1, 6, n),
            "M": rng.integers(1, 6, n),
            "L": rng.integers(1, 6, n),
            "E": rng.integers(1, 6, n),
            "segment": rng.choice(["Champions", "Lost", "Hibernating", "Promising New"], n),
        }
    )
    # The store carries ~3% missingness on every numeric column, by design.
    for column in ("recharge_count_90d", "days_since_last_topup", "tenure_months"):
        frame.loc[frame.sample(frac=0.03, random_state=1).index, column] = np.nan
    return frame


# --- The reconstructed summary ---------------------------------------------


def test_frequency_counts_repeats_not_transactions(base):
    """BG/NBD's frequency is purchases AFTER the first. Off by one here and
    every rate estimate is wrong by one transaction per subscriber."""
    summary = clv.summary_from_population(base)
    known = base["recharge_count_90d"].notna() & (base["recharge_count_90d"] > 0)
    expected = (base.loc[known, "recharge_count_90d"] - 1).to_numpy()
    assert summary.loc[known.to_numpy(), clv.FREQUENCY].to_numpy() == pytest.approx(expected)
    assert (summary[clv.FREQUENCY] >= 0).all()


def test_age_is_the_observation_window_not_tenure(base):
    """Pairing a 90-day count with a five-year T tells the model a weekly
    recharger transacts ten times a decade, and every predicted value
    collapses. T is capped at the window."""
    summary = clv.summary_from_population(base, window_days=90)
    assert summary[clv.AGE].max() <= 90
    assert (summary[clv.AGE] > 0).all()

    # A subscriber newer than the window keeps their true, shorter age.
    young = base.assign(tenure_months=1.0)
    assert clv.summary_from_population(young, window_days=90)[clv.AGE].max() == pytest.approx(30.0)


def test_recency_never_exceeds_age(base):
    """lifetimes does not validate this and produces nonsense if it is
    violated -- age at last purchase cannot exceed age."""
    summary = clv.summary_from_population(base)
    assert (summary[clv.RECENCY] <= summary[clv.AGE]).all()
    assert (summary[clv.RECENCY] >= 0).all()


def test_a_subscriber_with_no_repeat_has_zero_recency(base):
    single = base.assign(recharge_count_90d=1.0)
    summary = clv.summary_from_population(single)
    assert (summary[clv.FREQUENCY] == 0).all()
    assert (summary[clv.RECENCY] == 0).all()


def test_no_nan_survives_the_summary(base):
    """REGRESSION. The store carries 3% missingness and lifetimes does not warn
    about a NaN -- it fails to converge on the FIRST likelihood evaluation with
    `NaN result encountered`, which reads like a modelling problem and is a
    data problem."""
    summary = clv.summary_from_population(base)
    assert summary[[clv.FREQUENCY, clv.RECENCY, clv.AGE, clv.MONETARY]].notna().all().all()
    assert summary["is_imputed"].sum() > 0, "the fixture is supposed to carry missingness"


def test_the_fit_excludes_imputed_rows_but_scoring_does_not(base):
    """Parameters must not be shaped by the imputation's own median. Scoring
    everyone is right -- a subscriber with no ceiling has no constraint."""
    summary = clv.summary_from_population(base)
    complete = clv.complete_cases(summary)

    assert len(complete) < len(summary)
    assert (complete["is_imputed"] == 0).all()


def test_the_raw_recharge_count_cannot_be_substituted(base):
    """`frequency_raw` is the count divided by (1 + cv). BG/NBD needs repeat
    TRANSACTIONS and a penalised score is not one."""
    with pytest.raises(KeyError, match="RAW recharge count"):
        clv.summary_from_population(base.drop(columns=["recharge_count_90d"]))


# --- The fitters ------------------------------------------------------------


def test_bg_nbd_refuses_a_degenerate_fit(base):
    """REGRESSION, and it cost a run. A penalizer shrinks a and b toward zero;
    once b < 1 the dropout Beta is U-shaped and lifetimes' conditional
    expectation takes the log of a negative number, returning NaN for every
    zero-repeat customer rather than raising. Measured on Online Retail II:
    penalizer 0.01 gave b=0.570 and 844 NaN of 4,933."""
    summary = clv.complete_cases(clv.summary_from_population(base))

    model = clv.fit_bg_nbd(summary)  # the default is 0.0 and must be clean
    probe = model.predict(30.0, summary[clv.FREQUENCY], summary[clv.RECENCY], summary[clv.AGE])
    assert not np.isnan(np.asarray(probe, dtype="float64")).any()


def test_gamma_gamma_checks_its_own_assumption(base):
    """It requires frequency and monetary value to be uncorrelated. If they are
    not, it mis-prices exactly the high-value subscribers the budget ceiling
    exists to protect."""
    summary = clv.complete_cases(clv.summary_from_population(base))
    model = clv.fit_gamma_gamma(summary)
    assert hasattr(model, "frequency_monetary_correlation_")
    assert abs(model.frequency_monetary_correlation_) <= 1.0


def test_gamma_gamma_refuses_a_base_with_no_repeat_buyers(base):
    single = base.assign(recharge_count_90d=1.0)
    summary = clv.summary_from_population(single)
    with pytest.raises(ValueError, match="no repeat customers"):
        clv.fit_gamma_gamma(summary)


def test_clv_is_discounted(base):
    """An undiscounted 12-month CLV overstates the ceiling by about 6% at 1%
    monthly, which sounds small until it is 15% of a number the pricing engine
    is allowed to spend."""
    summary = clv.summary_from_population(base)
    complete = clv.complete_cases(summary)
    bgf, ggf = clv.fit_bg_nbd(complete), clv.fit_gamma_gamma(complete)

    short = clv.predict_clv(bgf, ggf, summary, months=6)
    long = clv.predict_clv(bgf, ggf, summary, months=12)

    assert (long >= short).all(), "a longer horizon cannot be worth less"
    assert long.median() < 2 * short.median(), "discounting is not being applied"


def test_every_subscriber_gets_a_value(base):
    """A NaN CLV means no budget ceiling, which means no constraint at all --
    strictly worse than an estimated one."""
    summary = clv.summary_from_population(base)
    complete = clv.complete_cases(summary)
    value = clv.predict_clv(clv.fit_bg_nbd(complete), clv.fit_gamma_gamma(complete), summary)
    assert value.notna().all()
    assert (value >= 0).all()
    assert len(value) == len(base)


def test_the_ceiling_is_the_configured_fraction(base):
    """The constraint that makes the pricing engine defensible to a CFO. It
    reads conf/pricing.yaml, the same key the proposal-consistency test pins."""
    fraction = load_conf("pricing")["guardrails"]["clv_ceiling"]["max_fraction_of_clv"]
    value = pd.Series([480.0, 100.0, 0.0])

    ceiling = clv.retention_budget_ceiling(value)

    assert ceiling.iloc[0] == pytest.approx(480.0 * fraction)
    assert ceiling.iloc[0] == pytest.approx(72.0), "the 40 LYD ARPU case must be 72 LYD"
    assert (ceiling <= value).all()


def test_the_ibm_benchmark_reports_no_rank_metric():
    """A Spearman over two independently sorted quantile vectors is exactly
    1.000 for ANY two distributions, because quantiles are sorted by
    construction. The first version reported it, and 1.000 beside the word
    Spearman reads as a perfect result."""
    rng = np.random.default_rng(0)
    ours = pd.Series(rng.lognormal(5, 1.2, 5000))
    theirs = pd.Series(rng.uniform(2000, 6000, 7000))  # deliberately unlike

    metrics = clv.benchmark_against_ibm(ours, theirs)

    assert "spearman" not in metrics, "a metric that cannot fail is not evidence"
    assert metrics["mae_scaled"] > 0
    assert metrics["spread_ratio"] > 1, "a lognormal is more dispersed than a uniform"


# --- Segments ---------------------------------------------------------------


def test_the_design_matrix_is_scaled(base):
    """K-Means on a Euclidean metric would otherwise cluster almost entirely on
    whichever dimension happened to have the largest variance."""
    X = segmentation.design(base)
    assert list(X.columns) == list(segmentation.DIMENSIONS)
    assert X.mean().abs().max() < 1e-9
    assert X.std().between(0.9, 1.1).all()


def test_missing_quintiles_are_refused(base):
    with pytest.raises(KeyError, match="RFM-LE quintiles"):
        segmentation.design(base.drop(columns=["E"]))


def test_the_elbow_is_computed_not_eyeballed():
    """It is still a heuristic -- that is why silhouette decides -- but at least
    it is the SAME heuristic every time."""
    scores = pd.DataFrame({"k": [3, 4, 5, 6, 7], "inertia": [1000.0, 400.0, 250.0, 220.0, 210.0]})
    assert segmentation._elbow(scores) == 4


def test_kmeans_picks_k_by_silhouette(base):
    model, scores, by_elbow = segmentation.fit_kmeans(base, k_search=(3, 4, 5))
    best = int(scores.loc[scores["silhouette"].idxmax(), "k"])

    assert model.n_clusters == best, "silhouette decides, not the elbow"
    assert set(scores.columns) >= {"k", "inertia", "silhouette", "davies_bouldin"}
    assert by_elbow in (3, 4, 5)


def test_pca_reports_explained_variance(base):
    model, projected, loadings = segmentation.fit_pca(base, n_components=2)
    assert projected.shape == (len(base), 2)
    assert loadings.shape == (5, 2)
    assert 0 < model.explained_variance_ratio_.sum() <= 1.0


def test_the_dendrogram_states_its_own_natural_cut(base):
    """The uncomfortable question this module exists for: are the eight
    business segments a shape in the data, or a grid we imposed on it?"""
    matrix, sampled = segmentation.fit_hierarchical(base, sample_size=500)
    frame = segmentation.dendrogram_data(matrix)

    assert len(sampled) == 500
    assert "natural_clusters" in frame.attrs
    assert 2 <= frame.attrs["natural_clusters"] <= 12
    assert (frame["gap_to_next"] >= 0).all()


def test_rules_and_clusters_are_compared_label_invariantly(base):
    """The two labellings share no vocabulary -- cluster 3 is not trying to be
    `At-Risk Valuable` -- so agreement needs a mapping, and the mapping-free
    metrics are reported beside it."""
    labels = pd.Series(np.resize([0, 1, 2], len(base)))
    crosstab = segmentation.compare_rules_vs_clusters(base["segment"], labels)

    for key in ("disagreement_share", "adjusted_rand", "normalised_mutual_info", "cluster_purity"):
        assert key in crosstab.attrs
    assert 0 <= crosstab.attrs["disagreement_share"] <= 1


def test_identical_labellings_agree_completely(base):
    """The sanity end of the scale: a clustering that reproduces the rules
    exactly must score 0% disagreement and adjusted Rand 1."""
    codes = pd.Series(pd.Categorical(base["segment"]).codes)
    crosstab = segmentation.compare_rules_vs_clusters(base["segment"], codes)

    assert crosstab.attrs["disagreement_share"] == pytest.approx(0.0)
    assert crosstab.attrs["adjusted_rand"] == pytest.approx(1.0)


def test_mismatched_label_lengths_are_refused(base):
    with pytest.raises(ValueError, match="rule labels against"):
        segmentation.compare_rules_vs_clusters(base["segment"], pd.Series([0, 1, 2]))
