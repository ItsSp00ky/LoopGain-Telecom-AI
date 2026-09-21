"""T12: the parts of the sequence benchmark that hold without a neural network.

The shaping is what can go silently wrong here. A model that reads the two months in
the wrong order, or standardises with the test customers' own statistics, still trains
and still prints a number, and the number is meaningless. Those are the tests below.

The Keras run itself is one test at the end, skipped when the experiments group is not
installed, so the default suite stays green on a fresh clone.
"""

import sys

import numpy as np
import pytest

from prepaid_churn.sequence import (
    SEED,
    STEPS,
    benchmark,
    benchmark_report,
    fit_standardiser,
    raw_sequences,
    sequence_bases,
    standardise,
)
from prepaid_churn.windows import TENURE_FEATURE, build_datasets


@pytest.fixture
def datasets(population):
    return build_datasets(population)


def test_the_sequence_holds_the_measures_of_both_months_only(datasets):
    """The T5 features are the movement between the months; giving them to the LSTM too
    would hand it the answer it is meant to derive from the sequence."""
    bases = sequence_bases(datasets["train"])
    assert "arpu" in bases and "total_rech_num" in bases
    assert not [base for base in bases if base.startswith(("diff_", "trend_"))]
    for base in bases:
        assert all(f"{step}_{base}" in datasets["train"].columns for step in STEPS)


def test_the_previous_month_is_the_first_step(datasets):
    """Reversing the two steps is invisible in every metric and wrong in every prediction."""
    train = datasets["train"]
    bases = sequence_bases(train)
    sequences = raw_sequences(train, bases)
    assert sequences.shape == (len(train), len(STEPS), len(bases) + 1)
    position = bases.index("arpu")
    assert sequences[0, 0, position] == train["prev_arpu"].iloc[0]
    assert sequences[0, 1, position] == train["cur_arpu"].iloc[0]
    # Tenure is one number per customer, so it is the last measure on both steps.
    assert sequences[0, 0, -1] == sequences[0, 1, -1] == train[TENURE_FEATURE].iloc[0]


def test_the_scale_comes_from_training_customers_only(datasets):
    """Fitting it on the batch being scored is the leak this function exists to avoid."""
    bases = sequence_bases(datasets["train"])
    train = raw_sequences(datasets["train"], bases)
    standardiser = fit_standardiser(train)
    scaled_train = standardise(train, standardiser)
    assert not np.isnan(scaled_train).any()
    flat = scaled_train.reshape(-1, scaled_train.shape[-1])
    assert np.allclose(flat.mean(axis=0), 0, atol=1e-6)
    assert np.allclose(flat.std(axis=0)[flat.std(axis=0) > 0], 1, atol=1e-6)

    test = raw_sequences(datasets["test"], bases)
    scaled_test = standardise(test, standardiser)
    assert not np.isnan(scaled_test).any()
    # The test customers move the mean; if they had been fitted on, this would be 0.
    assert not np.allclose(scaled_test.reshape(-1, scaled_test.shape[-1]).mean(axis=0), 0)


def test_a_missing_value_becomes_the_training_median(datasets):
    bases = sequence_bases(datasets["train"])
    train = raw_sequences(datasets["train"], bases)
    standardiser = fit_standardiser(train)
    with_gap = train.copy()
    with_gap[0, 0, 0] = np.nan
    scaled = standardise(with_gap, standardiser)
    expected = (standardiser["median"][0] - standardiser["mean"][0]) / standardiser["spread"][0]
    assert scaled[0, 0, 0] == pytest.approx(expected)


def test_a_missing_keras_says_what_to_run(monkeypatch):
    from prepaid_churn import sequence

    monkeypatch.setitem(sys.modules, "keras", None)
    with pytest.raises(ImportError, match="uv sync --group experiments"):
        sequence.build_model(3)


def test_the_benchmark_scores_the_test_window_once(trained):
    """The whole path on the hand-made population: train, calibrate, score, report."""
    pytest.importorskip("keras", reason="the experiments group is not installed")
    result = benchmark(
        trained["datasets"], trained["gate"], trained["models"]["logistic_regression"], seed=SEED
    )
    assert 0.0 <= result["test_metrics"]["pr_auc"] <= 1.0
    assert 0.0 <= result["capture"] <= 1.0
    assert set(result["thresholds"]) == {
        "capture",
        "better_than_chance",
        "better_than_baseline",
        "calibration",
    }
    assert result["thresholds"]["better_than_baseline"]["required"].startswith(">")

    report = benchmark_report(result, trained["gate"], trained["datasets"])
    assert report.startswith("# T12 sequence benchmark")
    assert "Would this model be released?" in report
    assert "What this does not settle" in report
    assert f"Seed {SEED}" in report
