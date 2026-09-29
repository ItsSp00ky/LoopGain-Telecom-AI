import pandas as pd
import pytest

from prepaid_churn.data import split_month
from prepaid_churn.windows import (
    LABEL,
    SPLITS,
    TENURE_FEATURE,
    WINDOW_A,
    WINDOW_B,
    active_in_current_month,
    build_datasets,
    dataset_report,
    high_value,
    split_customers,
    window_features,
    window_label,
)


def test_window_features_use_only_the_two_window_months(population):
    features = window_features(population, WINDOW_A)
    assert TENURE_FEATURE in features.columns
    assert "prev_onnet_mou" in features.columns
    assert "cur_days_since_last_rech" in features.columns
    assert not any(column.endswith(("_8", "_9")) for column in features.columns)


@pytest.mark.parametrize(("window", "later_month"), [(WINDOW_A, 8)])
def test_changing_later_months_does_not_change_features(population, window, later_month):
    changed = population.copy()
    for column in population.columns:
        if split_month(column)[1] == later_month:
            changed[column] = 999
    pd.testing.assert_frame_equal(
        window_features(changed, window), window_features(population, window)
    )


def test_changing_the_kaggle_label_does_not_change_window_b_features(population):
    changed = population.assign(churn_probability=1 - population["churn_probability"])
    pd.testing.assert_frame_equal(
        window_features(changed, WINDOW_B), window_features(population, WINDOW_B)
    )


def test_windows_have_identical_feature_columns(population):
    assert list(window_features(population, WINDOW_A).columns) == list(
        window_features(population, WINDOW_B).columns
    )


def test_labels(raw):
    from prepaid_churn.clean import clean

    cleaned = clean(raw)
    # Window A: our rule on month 8. Customers 1 and 3 are inactive in month 8.
    assert window_label(cleaned, WINDOW_A).tolist() == [0, 1, 0, 1]
    # Window B: Kaggle's month 9 label.
    assert window_label(cleaned, WINDOW_B).tolist() == [0, 1, 0, 0]


def test_customers_silent_in_the_current_month_are_not_eligible(raw):
    from prepaid_churn.clean import clean

    cleaned = clean(raw)
    assert active_in_current_month(cleaned, WINDOW_A).tolist() == [True, True, True, True]
    assert active_in_current_month(cleaned, WINDOW_B).tolist() == [True, False, True, False]


def test_split_is_disjoint_stratified_and_reproducible(population):
    split = split_customers(population)
    assert split.value_counts().to_dict() == {"train": 140, "validation": 30, "test": 30}
    label = window_label(population, WINDOW_A)
    for name in SPLITS:
        assert label[split.eq(name)].mean() == pytest.approx(0.5)
    pd.testing.assert_series_equal(split, split_customers(population))


def test_no_customer_in_more_than_one_dataset(population):
    datasets = build_datasets(population)
    ids = [set(datasets[name]["id"]) for name in SPLITS]
    assert not (ids[0] & ids[1] or ids[0] & ids[2] or ids[1] & ids[2])


def test_datasets_follow_the_windows_and_eligibility(population):
    datasets = build_datasets(population)
    # Everyone is active in month 7, so train keeps all 140 train customers.
    assert len(datasets["train"]) == 140
    # Half the customers are silent in month 8, so test keeps only the active half.
    assert len(datasets["test"]) == 15
    # Only customers 0 and 2 are active in month 8; some copies of customer 0 churn in month 9.
    assert set(datasets["test"][LABEL]) == {0, 1}
    assert list(datasets["train"].columns) == list(datasets["test"].columns)


def test_high_value_keeps_the_top_30_percent(population):
    keep = high_value(population, WINDOW_A)
    assert keep.mean() == pytest.approx(0.30)
    amounts = population["total_rech_amt_7"]
    assert amounts[keep].min() > amounts[~keep].max()


def test_high_value_datasets_are_smaller(population):
    everyone = build_datasets(population)
    top = build_datasets(population, high_value_only=True)
    assert all(len(top[name]) < len(everyone[name]) for name in SPLITS)


def test_dataset_report(population):
    report = dataset_report(population, build_datasets(population))
    assert "| test | B (7, 8 -> 9) | 30 | 15 | 15 |" in report
