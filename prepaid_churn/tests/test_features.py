import pytest

from prepaid_churn.clean import clean
from prepaid_churn.features import FEATURES, add_features
from prepaid_churn.schema import validate
from prepaid_churn.windows import WINDOW_A, WINDOW_B, window_features


@pytest.fixture
def window_a(raw):
    return add_features(window_features(clean(validate(raw)), WINDOW_A))


@pytest.fixture
def window_b(raw):
    return add_features(window_features(clean(validate(raw)), WINDOW_B))


def test_every_feature_is_added_and_described(window_a):
    assert set(FEATURES) <= set(window_a.columns)
    assert all(description.strip() for description in FEATURES.values())
    assert not window_a[list(FEATURES)].isna().any().any()


def test_month_over_month_differences(window_a):
    customer = window_a.loc[0]
    assert customer["diff_arpu"] == -10
    assert customer["diff_total_og_mou"] == 4
    assert customer["diff_total_mou"] == 4
    assert customer["diff_data_mb"] == -80
    assert customer["diff_total_rech_num"] == 1


def test_trends(window_a):
    customer = window_a.loc[0]
    assert customer["trend_total_og_mou"] == pytest.approx(34 / 64)
    assert customer["trend_total_ic_mou"] == 0.5
    # Customer 2 never used data: nothing changed, so the trend is neutral.
    assert window_a.loc[2, "trend_data_mb"] == 0.5


def test_shares(window_a, window_b):
    customer = window_a.loc[0]
    assert customer["cur_onnet_share"] == pytest.approx(12 / 34)
    assert customer["diff_onnet_share"] == pytest.approx(12 / 34 - 10 / 30)
    assert customer["cur_incoming_share"] == pytest.approx(15 / 49)
    # Customer 1 has no voice record in month 8: shares fall back to neutral.
    assert window_b.loc[1, "cur_onnet_share"] == 0.5
    assert window_b.loc[1, "cur_incoming_share"] == 0.5


def test_recency_looks_back_over_both_months(window_b):
    # Recharged on 15 August: 16 days to the month end.
    assert window_b.loc[0, "days_since_last_rech_window"] == 16
    # No recharge in August, last one on 15 July: 31 + 16 days.
    assert window_b.loc[1, "days_since_last_rech_window"] == 47
    # No data pack in July or August: 31 + 31 days, i.e. none in the window.
    assert window_b.loc[1, "days_since_last_rech_data_window"] == 62
