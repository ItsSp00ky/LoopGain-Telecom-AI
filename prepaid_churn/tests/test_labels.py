from prepaid_churn.labels import recharge_inactive, usage_inactive


def test_usage_inactive(raw):
    assert usage_inactive(raw, 8).tolist() == [False, True, False, True]
    assert usage_inactive(raw, 6).tolist() == [False, False, False, False]


def test_recharge_inactive_treats_missing_data_recharge_as_none(raw):
    assert recharge_inactive(raw, 8).tolist() == [False, True, False, False]
