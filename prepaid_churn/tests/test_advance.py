from copy import deepcopy

import numpy as np
import pandas as pd
import pytest

from prepaid_churn.advance import (
    AIRTIME,
    DATA,
    MAX_DEBT_FRACTION,
    AdviceError,
    advance_products,
    advertised_debts,
    advice_report,
    advise,
    affordability_ceiling,
    airtime_limit,
    basis_sensitivity,
    data_advance_advised,
    residual_after_clearing,
    smallest_card,
    topup_by_month,
    typical_topup,
    usual_card,
    zero_residual_products,
)
from prepaid_churn.clean import clean
from prepaid_churn.operator_market import InvalidCatalogueError, load_market
from prepaid_churn.schema import validate
from prepaid_churn.windows import WINDOW_A


@pytest.fixture
def market():
    return load_market()


# ---------------------------------------------------------------------------
# The products, as the operator documents them
# ---------------------------------------------------------------------------


def test_the_two_products_come_from_the_operator_file(market):
    products = advance_products(market)
    assert products[AIRTIME] == [1.0, 3.0, 5.0]
    assert products[DATA] == 5.0


def test_a_market_without_the_products_is_refused(market):
    for key in ("airtime_advance", "data_advance"):
        broken = deepcopy(market)
        del broken[key]
        with pytest.raises(InvalidCatalogueError, match="emergency credit"):
            advance_products(broken)


def test_an_impossible_denomination_is_refused(market):
    broken = deepcopy(market)
    broken["airtime_advance"]["denominations_lyd"] = [0, 3]
    with pytest.raises(InvalidCatalogueError, match="positive denominations"):
        advance_products(broken)


# ---------------------------------------------------------------------------
# The zero-residual finding
# ---------------------------------------------------------------------------


def test_every_five_dinar_debt_consumes_the_whole_smallest_card(market):
    """The structural finding, computed from the operator's own numbers rather than asserted.

    Both 5 LYD debts zero the card: the flat data advance, and the top airtime rung.
    """
    assert smallest_card(market) == 5.0
    assert residual_after_clearing(5.0, 5.0) == 0.0
    assert zero_residual_products(market) == [
        "airtime advance of 5 LYD",
        "data advance of 5 LYD",
    ]


def test_the_ceiling_keeps_a_five_dinar_debt_away_from_a_five_dinar_recharger(market):
    """The customer at the recharge floor is exactly the one the ceiling protects."""
    products = advance_products(market)
    at_the_floor = affordability_ceiling(pd.Series([smallest_card(market)]))
    assert airtime_limit(at_the_floor, products[AIRTIME]).iloc[0] == 3.0
    assert not data_advance_advised(at_the_floor, products[DATA]).any()


def test_the_small_airtime_rungs_leave_the_customer_something(market):
    card = smallest_card(market)
    residuals = {
        label: residual_after_clearing(debt, card) for label, debt in advertised_debts(market)
    }
    assert residuals["airtime advance of 1 LYD"] == 4.0
    assert residuals["airtime advance of 3 LYD"] == 2.0
    assert residuals["airtime advance of 5 LYD"] == 0.0


def test_a_bigger_smallest_card_would_retire_the_finding(market):
    """If the operator ever sold a 3 LYD card the argument changes, so it is not hardcoded."""
    changed = deepcopy(market)
    changed["recharge_cards"]["values_lyd"] = [10, 20, 40]
    assert zero_residual_products(changed) == []


# ---------------------------------------------------------------------------
# The ceiling
# ---------------------------------------------------------------------------


def test_the_ceiling_is_a_fraction_of_the_typical_topup():
    topup = pd.Series([5.0, 10.0, 40.0])
    np.testing.assert_allclose(affordability_ceiling(topup), [3.0, 6.0, 24.0])


def test_an_unknown_topup_gives_no_capacity():
    """Unknown recharge behaviour is not evidence of capacity to repay."""
    assert affordability_ceiling(pd.Series([np.nan])).iloc[0] == 0.0


@pytest.mark.parametrize("fraction", [1.0, 1.5, 0.0, -0.2])
def test_a_fraction_of_one_or_more_is_refused(fraction):
    """At 1.0 a debt equal to the typical top-up is allowed, which is the trap."""
    with pytest.raises(AdviceError, match="above 0 and below 1"):
        affordability_ceiling(pd.Series([10.0]), fraction)


def test_the_default_fraction_stays_below_one():
    assert 0.0 < MAX_DEBT_FRACTION < 1.0


# ---------------------------------------------------------------------------
# The advised denomination
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ceiling", "expected"),
    [
        (0.0, 0.0),
        (0.9, 0.0),  # below the smallest rung: decline
        (1.0, 1.0),  # exactly the rung is allowed
        (2.9, 1.0),  # no 2 LYD advance exists to round up to
        (3.0, 3.0),
        (4.9, 3.0),
        (5.0, 5.0),
        (50.0, 5.0),  # never beyond what the operator sells
    ],
)
def test_only_denominations_the_operator_sells_are_advised(ceiling, expected, market):
    limit = airtime_limit(pd.Series([ceiling]), advance_products(market)[AIRTIME])
    assert limit.iloc[0] == expected


def test_the_flat_data_advance_is_advise_or_decline(market):
    price = advance_products(market)[DATA]
    advised = data_advance_advised(pd.Series([2.9, 5.0, 12.0]), price)
    assert list(advised) == [False, True, True]


def test_the_data_advance_needs_a_much_larger_topup_than_the_airtime_one(market):
    """5 LYD flat at a 0.6 ceiling means a typical top-up of at least 8.33 LYD."""
    products = advance_products(market)
    needed = products[DATA] / MAX_DEBT_FRACTION
    assert needed == pytest.approx(8.3333, abs=1e-4)
    assert data_advance_advised(affordability_ceiling(pd.Series([needed])), products[DATA]).all()
    just_below = affordability_ceiling(pd.Series([needed - 0.01]))
    assert not data_advance_advised(just_below, products[DATA]).any()


# ---------------------------------------------------------------------------
# The typical top-up
# ---------------------------------------------------------------------------


def _window_frame(prev_amount, prev_count, cur_amount, cur_count) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "prev_total_rech_amt": prev_amount,
            "prev_total_rech_num": prev_count,
            "cur_total_rech_amt": cur_amount,
            "cur_total_rech_num": cur_count,
        }
    )


def test_the_two_months_are_averaged():
    """One quiet month does not decide the advice alone (decision 50)."""
    frame = _window_frame([100.0], [2], [30.0], [3])  # 50 per top-up, then 10
    assert typical_topup(frame, rate=1.0).iloc[0] == pytest.approx(30.0)


def test_a_month_without_a_recharge_is_skipped_not_counted_as_zero():
    frame = _window_frame([0.0], [0], [40.0], [2])
    assert typical_topup(frame, rate=1.0).iloc[0] == pytest.approx(20.0)


def test_no_recharge_in_either_month_leaves_no_basis():
    frame = _window_frame([0.0], [0], [0.0], [0])
    assert pd.isna(typical_topup(frame, rate=1.0).iloc[0])


def test_the_rate_converts_the_basis_into_lyd():
    frame = _window_frame([100.0], [1], [100.0], [1])
    assert typical_topup(frame, rate=0.074464).iloc[0] == pytest.approx(7.4464)


def test_the_typical_topup_becomes_the_card_the_customer_would_buy(market):
    """Nothing below the smallest card can be topped up at the operator (decision 49)."""
    cards = usual_card(pd.Series([1.2, 6.0, 7.6, 14.0, 0.0, np.nan]), market)
    assert cards.iloc[:4].tolist() == [5.0, 5.0, 10.0, 10.0]
    assert cards.iloc[4] == 0.0  # recharges worth nothing: no card is invented
    assert pd.isna(cards.iloc[5])  # no top-up, no card, no basis


def test_a_topup_below_the_smallest_card_is_advised_the_rung_that_card_allows(market):
    """A converted 1.2 LYD top-up was declined before; the 5 LYD card allows 3 LYD."""
    products = advance_products(market)
    ceiling = affordability_ceiling(usual_card(pd.Series([1.2]), market))
    assert airtime_limit(ceiling, products[AIRTIME]).iloc[0] == 3.0
    assert not data_advance_advised(ceiling, products[DATA]).any()


# ---------------------------------------------------------------------------
# End to end on the hand-made customers
# ---------------------------------------------------------------------------


@pytest.fixture
def advice(raw, market):
    return advise(clean(validate(raw)), WINDOW_A, market)


def test_every_customer_gets_one_row_and_one_reason(advice, raw):
    assert len(advice) == len(raw)
    assert advice["advice_reason_en"].str.len().gt(0).all()
    assert advice["advice_reason_ar"].str.len().gt(0).all()
    codes = {"no_recharge", "no_paid_topup", "below_smallest", "airtime_only", "both"}
    assert set(advice["advice_code"]) <= codes


def test_a_declined_customer_is_never_advised_a_limit(advice):
    declined = advice["airtime_limit_lyd"].eq(0)
    declined_codes = ["no_recharge", "no_paid_topup", "below_smallest"]
    assert advice.loc[declined, "advice_code"].isin(declined_codes).all()
    assert not advice.loc[declined, "data_advance_advised"].any()
    assert advice.loc[declined, "airtime_residual_lyd"].isna().all()


def test_an_advised_limit_always_leaves_the_customer_something(advice):
    """The whole purpose of the ceiling, asserted on every advised row."""
    advised = advice["airtime_limit_lyd"].gt(0)
    residual = advice.loc[advised, "airtime_residual_lyd"]
    assert (residual > 0).all()
    assert (
        advice.loc[advised, "airtime_limit_lyd"] <= advice.loc[advised, "typical_card_lyd"]
    ).all()


def test_the_advice_reads_the_card_and_declines_a_window_that_paid_nothing(raw, market):
    """Small paid top-ups get the rung of the smallest card (decision 49).

    A window whose recharges were worth nothing is declined, while a month worth nothing
    beside a paid one is averaged with it (decision 50).
    """
    paid = raw.copy()
    paid["total_rech_amt_6"] = [80, 200, 0, 0]  # 20, 100, 0 and 0 per recharge
    paid["total_rech_amt_7"] = [100, 100, 0, 400]  # 20, 100, 0 and 400 per recharge
    advice = advise(clean(validate(paid)), WINDOW_A, market)
    assert advice["typical_card_lyd"].tolist() == [5.0, 10.0, 0.0, 20.0]
    assert advice["airtime_limit_lyd"].tolist() == [3.0, 5.0, 0.0, 5.0]
    assert advice["advice_code"].tolist() == ["airtime_only", "both", "no_paid_topup", "both"]
    residual = advice["airtime_residual_lyd"]
    assert [residual[0], residual[1], residual[3]] == [2.0, 5.0, 15.0]


def test_the_advised_limit_never_exceeds_the_ceiling(advice):
    assert (advice["airtime_limit_lyd"] <= advice["affordability_ceiling_lyd"] + 1e-9).all()


def test_the_data_advance_is_only_advised_alongside_an_airtime_limit(advice):
    """5 LYD is the top rung, so anyone who clears it clears the airtime advance too."""
    assert advice.loc[advice["data_advance_advised"], "airtime_limit_lyd"].eq(5.0).all()


def test_nothing_in_the_advice_grants_anything(advice):
    """T19 advises; decision 14 keeps a person in the loop."""
    assert "granted" not in advice.columns
    assert "status" not in advice.columns


def test_both_months_travel_with_the_advice(advice):
    """A reviewer should see the behaviour the advice was read from, not only the verdict."""
    assert {"topup_prev_lyd", "topup_cur_lyd"} <= set(advice.columns)
    months = advice[["topup_prev_lyd", "topup_cur_lyd"]]
    average = months.mean(axis=1, skipna=True)
    pd.testing.assert_series_equal(advice["typical_topup_lyd"], average, check_names=False)
    cards = usual_card(average, load_market())
    pd.testing.assert_series_equal(advice["typical_card_lyd"], cards, check_names=False)


def test_a_month_with_no_recharge_is_empty_rather_than_zero():
    frame = _window_frame([0.0], [0], [40.0], [2])
    months = topup_by_month(frame, rate=1.0)
    assert pd.isna(months["topup_prev_lyd"].iloc[0])
    assert months["topup_cur_lyd"].iloc[0] == pytest.approx(20.0)


def test_the_sensitivity_table_shows_the_basis_choice_changing_the_answer(advice, market):
    """The choice standing in for the mode is an assumption, so its effect is reported."""
    table = basis_sensitivity(advice, market)
    assert list(table["basis"]) == [
        "quieter month",
        "mean of both months (used)",
        "busier month",
    ]
    # The quieter month can never advise more than the busier one.
    assert table["median_topup_lyd"].is_monotonic_increasing
    assert table["smallest_card"].between(0, 1).all()
    assert table["declined"].is_monotonic_decreasing
    assert table["data_advance_advised"].is_monotonic_increasing
    # The mean is used (decision 50); the quieter month stays as the cautious reference.
    assert table.loc[0, "declined"] == table["declined"].max()


def test_the_report_states_every_assumption_and_the_finding(advice, market):
    report = advice_report(advice, market, "test.csv")
    for phrase in (
        "advice, not a grant",
        "zero-residual",
        "data advance is exactly the size of the smallest card",
        "No repayment model",
        "modal",
        "disincentive to recharge, not a locked door",
        "How much the basis choice matters",
        "translated into the card the customer would buy",
        "What the rule advises",
    ):
        assert phrase in report, f"the report no longer explains {phrase!r}"
    assert f"{MAX_DEBT_FRACTION:g}" in report
    assert (
        "the other Libyan operator" in report
    )  # the correction that its credit loan does not transfer
