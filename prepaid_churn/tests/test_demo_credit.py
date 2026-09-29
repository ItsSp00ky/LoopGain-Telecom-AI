"""The Subscriber screen shows T19's emergency credit advice (tickets T14 and T19)."""

import pandas as pd
import pytest

from prepaid_churn.advance import REASONS
from prepaid_churn.data import PROJECT_ROOT
from prepaid_churn.demo import DemoPaths, campaign_directories, credit_advice, load_demo

CODES = ["both", "airtime_only", "no_recharge"]


@pytest.fixture
def paths(tmp_path):
    """A tiers-only checkout: a portfolio, an operator view and the advice beside it."""
    ids = ["0001", "NA", "0003"]
    pd.DataFrame(
        {
            "subscriber_id": ids,
            "value_tier": ["high", "low", "medium"],
            "monthly_spend_lyd": [40.0, 20.0, 5.0],
        }
    ).to_csv(tmp_path / "tiers.csv", index=False)
    pd.DataFrame(
        {
            "id": ids,
            "monthly_spend_lyd": [40.0, 20.0, 5.0],
            "usual_card_lyd": [10.0, 5.0, None],
            "bundle_held": ["PAYG", "PAYG", "PAYG"],
            "bundle_price_lyd": [None, None, None],
        }
    ).to_csv(tmp_path / "operator_view.csv", index=False)
    pd.DataFrame(
        {
            "id": ids,
            "topup_prev_lyd": [21.5, 3.2, None],
            "topup_cur_lyd": [5.2, 4.1, None],
            "typical_topup_lyd": [13.35, 3.65, None],
            "typical_card_lyd": [10.0, 5.0, None],
            "affordability_ceiling_lyd": [6.0, 3.0, 0.0],
            "airtime_limit_lyd": [5.0, 3.0, 0.0],
            "airtime_residual_lyd": [5.0, 2.0, None],
            "data_advance_advised": [True, False, False],
            "advice_code": CODES,
            "advice_reason_en": [REASONS[code][0] for code in CODES],
            "advice_reason_ar": [REASONS[code][1] for code in CODES],
        }
    ).to_csv(tmp_path / "advance.csv", index=False)
    return DemoPaths(
        portfolio_path=tmp_path / "tiers.csv",
        view_path=tmp_path / "operator_view.csv",
        campaign_dir=tmp_path / "campaign",
        bundle_dir=tmp_path / "bundle",
    )


@pytest.fixture
def subscriber_screen(paths, monkeypatch):
    """Open the real Subscriber page on one customer, over the hand-made files."""
    from streamlit.testing.v1 import AppTest

    monkeypatch.syspath_prepend(str(PROJECT_ROOT / "app"))
    import _shared

    monkeypatch.setattr(DemoPaths, "from_environment", classmethod(lambda cls: paths))
    monkeypatch.setattr(
        _shared, "campaign_directories", lambda: campaign_directories(paths.campaign_dir.parent)
    )
    _shared.refresh()

    def open_on(subscriber_id):
        page = PROJECT_ROOT / "app" / "pages" / "2_Subscriber.py"
        app = AppTest.from_file(str(page), default_timeout=30)
        app.session_state["subscriber_id"] = subscriber_id
        app.run()
        assert not app.exception, [error.message for error in app.exception]
        return app

    yield open_on
    _shared.refresh()


def test_the_advice_is_read_from_beside_the_operator_view(paths):
    assert paths.advice_path == paths.view_path.parent / "advance.csv"
    advice = credit_advice(load_demo(paths), "0001")
    assert advice["airtime_limit_lyd"] == 5.0
    assert bool(advice["data_advance_advised"]) is True
    assert advice["advice_reason_en"] == REASONS["both"][0]


def test_the_literal_id_na_keeps_its_advice(paths):
    assert credit_advice(load_demo(paths), "NA")["advice_code"] == "airtime_only"


def test_an_unknown_subscriber_has_no_advice(paths):
    assert credit_advice(load_demo(paths), "9999") is None


def test_a_checkout_without_advice_loads_and_reports_nothing_missing_for_it(paths):
    paths.advice_path.unlink()
    demo = load_demo(paths)
    assert credit_advice(demo, "0001") is None
    assert "credit advice" not in {what for what, _ in demo.missing}


def test_the_subscriber_screen_shows_the_advised_limits_and_the_reason(subscriber_screen):
    app = subscriber_screen("0001")
    assert "Emergency credit" in [header.value for header in app.subheader]
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics["Card the advice reads"] == "10 LYD"
    assert metrics["Airtime advance"] == "5 LYD"
    assert metrics["Data advance"] == "Advised"
    shown = [element.value for element in app.markdown]
    assert any(REASONS["both"][0] in value for value in shown)
    assert any(REASONS["both"][1] in value and "dir='rtl'" in value for value in shown)


def test_a_customer_with_no_recharge_is_advised_nothing(subscriber_screen):
    metrics = {metric.label: metric.value for metric in subscriber_screen("0003").metric}
    assert metrics["Airtime advance"] == "None"
    assert metrics["Data advance"] == "Not advised"


def test_without_advice_the_screen_names_the_command(subscriber_screen, paths):
    paths.advice_path.unlink()
    app = subscriber_screen("0001")
    assert any("uv run churn advance" in element.value for element in app.info)
