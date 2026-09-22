from dataclasses import replace

import pandas as pd
import pytest

from prepaid_churn.almadar import load_offers
from prepaid_churn.bundle import save_bundle
from prepaid_churn.campaign import (
    build_campaign,
    load_campaign,
    released_campaign,
    review_campaign,
    save_campaign,
)
from prepaid_churn.data import PROJECT_ROOT
from prepaid_churn.demo import (
    CAMPAIGN_DIR_VARIABLE,
    PORTFOLIO_VARIABLE,
    RISK_BANDS,
    VALUE_TIERS,
    DemoPaths,
    budget_preview,
    campaign_totals,
    customer_message,
    expected_churners,
    group_counts,
    guardrail_rejections,
    load_demo,
    offer_row,
    pending_proposals,
    revenue_at_risk,
    sms_parts,
    subscriber_view,
)
from prepaid_churn.retention import NO_OFFER, load_policy, propose

STAMP = "2026-09-20T12:00:00+00:00"
ARABIC = "المدار الجديد: هديتك نت الصباح."


@pytest.fixture
def offers():
    return load_offers()


@pytest.fixture
def policy():
    return replace(load_policy(), holdout_fraction=0.0)


@pytest.fixture
def customers(customers):
    """The shared four, with the last one made low risk.

    The campaign screens are about what the guardrails removed, so this file needs a
    customer the `low_risk` guard actually excludes. Everything else comes from the
    shared fixture in `conftest.py`.
    """
    return customers.assign(
        risk_band=["high", "high", "medium", "low"],
        value_tier=["high", "high", "medium", "very_low"],
        value_12m_base_lyd=[100.0, 80.0, 60.0, 40.0],
    )


@pytest.fixture
def built(tmp_path, bundle, customers, offers, policy, portfolio):
    """A checkout with a bundle, a reviewed campaign, a portfolio and an Almadar view."""
    save_bundle(bundle, tmp_path / "bundle")
    decisions, comparison = propose(customers, offers, policy)
    campaign = build_campaign(customers, decisions, comparison, offers, policy, STAMP)
    campaign = review_campaign(campaign, "Ali Marghem", "approved", ["0001"], reviewed_at=STAMP)
    campaign = review_campaign(campaign, "Ali Marghem", "rejected", ["0002"], reviewed_at=STAMP)
    save_campaign(campaign, tmp_path / "campaign")
    portfolio.to_csv(tmp_path / "tiers.csv", index=False)
    pd.DataFrame(
        {
            "id": ["0001", "0002", "NA", "0004"],
            "monthly_spend_lyd": [40.0, 30.0, 20.0, 5.0],
            "usual_card_lyd": [5.0, 5.0, 5.0, 5.0],
            "bundle_held": ["PAYG", "MO_20", "PAYG", "PAYG"],
            "bundle_price_lyd": [None, 35.0, None, None],
        }
    ).to_csv(tmp_path / "almadar_view.csv", index=False)
    return DemoPaths(
        portfolio_path=tmp_path / "tiers.csv",
        view_path=tmp_path / "almadar_view.csv",
        campaign_dir=tmp_path / "campaign",
        bundle_dir=tmp_path / "bundle",
    )


@pytest.fixture
def demo(built):
    return load_demo(built)


@pytest.fixture
def screen(built, monkeypatch):
    """Run the real page scripts over the same hand-made files as the pure-layer tests."""
    from streamlit.testing.v1 import AppTest

    monkeypatch.syspath_prepend(str(PROJECT_ROOT / "app"))
    import _shared

    monkeypatch.setattr(DemoPaths, "from_environment", classmethod(lambda cls: built))
    _shared.refresh()

    def open_page(name):
        app = AppTest.from_file(str(PROJECT_ROOT / "app" / name), default_timeout=30).run()
        assert not app.exception, [error.message for error in app.exception]
        return app

    yield open_page
    _shared.refresh()


@pytest.mark.parametrize(
    "name",
    [
        "Home.py",
        "pages/1_Overview.py",
        "pages/2_Subscriber.py",
        "pages/3_Campaign_builder.py",
        "pages/4_Message_preview.py",
    ],
)
def test_every_dashboard_page_renders(screen, name):
    screen(name)


def test_dashboard_review_requires_a_selection_and_refreshes_the_message(screen, built):
    app = screen("pages/3_Campaign_builder.py")
    original = built.campaign_path.read_bytes()
    app.text_input[0].set_value("Test reviewer")
    approve = next(button for button in app.button if button.label == "Approve selected")
    approve.click().run()
    assert not app.exception
    assert any("Choose the subscribers" in error.value for error in app.error)
    assert built.campaign_path.read_bytes() == original

    app.multiselect[0].set_value(["NA"])
    next(button for button in app.button if button.label == "Approve selected").click().run()
    assert not app.exception
    released = released_campaign(load_campaign(built.campaign_path))
    assert set(released.subscriber_id) == {"0001", "NA"}

    preview = screen("pages/4_Message_preview.py")
    assert set(preview.selectbox[0].options) == {"0001", "NA"}
    preview.selectbox[0].set_value("NA").run()
    arabic = preview.text_area[0].value
    assert any("\u0600" <= character <= "\u06ff" for character in arabic)
    preview.radio[0].set_value("en").run()
    assert not preview.exception and preview.text_area[0].value != arabic


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def test_a_complete_checkout_loads_everything(demo, bundle, offers):
    assert demo.missing == ()
    assert demo.model_version == bundle.version
    assert demo.has_risk is True
    assert len(demo.portfolio) == 4
    assert len(demo.decisions) == 4
    assert len(demo.offers) == len(offers)
    assert demo.campaign_path is not None


def test_literal_na_id_keeps_its_subscriber_view_and_recharge_card(demo):
    found = subscriber_view(demo, "NA")
    assert found is not None
    assert found["subscriber_id"] == "NA"
    assert found["usual_card_lyd"] == 5.0
    assert found["churn_probability"] == 0.3


def test_an_empty_checkout_names_the_command_for_each_missing_output(tmp_path):
    demo = load_demo(
        DemoPaths(
            portfolio_path=tmp_path / "none.csv",
            view_path=tmp_path / "none.csv",
            campaign_dir=tmp_path / "none",
            bundle_dir=tmp_path / "none",
        )
    )
    assert {what for what, _ in demo.missing} == {"portfolio", "bundle", "campaign", "almadar view"}
    assert all(how.startswith("uv run churn") for _, how in demo.missing)
    assert demo.has_risk is False
    # The catalogue is committed, so it is there even in an unbuilt checkout.
    assert not demo.offers.empty


# ---------------------------------------------------------------------------
# Headline numbers
# ---------------------------------------------------------------------------


def test_expected_churners_sums_probabilities_rather_than_counting_a_threshold(portfolio):
    assert expected_churners(portfolio) == pytest.approx(0.5 + 0.4 + 0.3)


def test_revenue_at_risk_is_weighted_by_each_customer_s_risk(portfolio):
    assert revenue_at_risk(portfolio) == pytest.approx(100 * 0.5 + 80 * 0.4 + 60 * 0.3)
    # Not the value of everyone who is at risk at all.
    assert revenue_at_risk(portfolio) != pytest.approx(240.0)


def test_headline_numbers_are_unavailable_rather_than_zero_without_risk(portfolio):
    tiers_only = portfolio.drop(columns=["churn_probability"])
    assert expected_churners(tiers_only) is None
    assert revenue_at_risk(tiers_only) is None
    assert expected_churners(None) is None


def test_groups_keep_a_readable_order_and_weight_the_money(portfolio):
    bands = group_counts(portfolio, "risk_band", RISK_BANDS)
    assert list(bands["group"]) == ["high", "medium", "already_silent"]
    assert bands.loc[bands["group"].eq("high"), "customers"].iloc[0] == 2
    assert bands.loc[bands["group"].eq("high"), "lyd_at_risk"].iloc[0] == pytest.approx(82.0)

    tiers = group_counts(portfolio, "value_tier", VALUE_TIERS)
    assert list(tiers["group"]) == ["high", "medium", "very_low"]
    assert tiers["monthly_spend_lyd"].sum() == pytest.approx(95.0)


def test_a_tiers_only_export_reports_no_bands_and_no_money_at_risk(portfolio):
    tiers_only = portfolio.drop(columns=["churn_probability", "risk_band"])
    assert group_counts(tiers_only, "risk_band", RISK_BANDS).empty
    tiers = group_counts(tiers_only, "value_tier", VALUE_TIERS)
    assert tiers["lyd_at_risk"].isna().all()
    assert tiers["customers"].sum() == 4


# ---------------------------------------------------------------------------
# One subscriber
# ---------------------------------------------------------------------------


def test_one_subscriber_joins_the_portfolio_the_decision_and_the_almadar_view(demo):
    subscriber = subscriber_view(demo, "0001")
    assert subscriber["risk_band"] == "high"
    assert subscriber["value_tier"] == "high"
    assert subscriber["bundle_held"] == "PAYG"
    assert subscriber["recommended_offer_id"] == "SABAH_1"
    assert subscriber["status"] == "approved"
    assert subscriber["reasons"] == ["No recharge for 21 days", "Outgoing minutes down 80%"]


def test_a_subscriber_with_no_reasons_gets_an_empty_list_not_a_blank_string(demo):
    assert subscriber_view(demo, "0004")["reasons"] == []


def test_the_literal_id_na_is_found_rather_than_read_as_missing(demo):
    """ "NA" is a real identifier in this data and pandas reads it as NaN by default."""
    subscriber = subscriber_view(demo, "NA")
    assert subscriber is not None
    assert subscriber["subscriber_id"] == "NA"


def test_an_unknown_subscriber_is_none(demo):
    assert subscriber_view(demo, "does-not-exist") is None


def test_a_single_customer_export_behaves_like_a_batch(tmp_path, bundle, portfolio):
    """The screen is opened on one customer, which is where the dtype bug lived."""
    one = portfolio.head(1)
    one.to_csv(tmp_path / "tiers.csv", index=False)
    demo = load_demo(
        DemoPaths(
            portfolio_path=tmp_path / "tiers.csv",
            view_path=tmp_path / "none.csv",
            campaign_dir=tmp_path / "none",
            bundle_dir=tmp_path / "none",
        )
    )
    subscriber = subscriber_view(demo, "0001")
    assert subscriber["risk_band"] == "high"
    assert isinstance(subscriber["churn_probability"], float)
    assert subscriber["reasons"] == ["No recharge for 21 days", "Outgoing minutes down 80%"]
    assert group_counts(demo.portfolio, "value_tier", VALUE_TIERS)["customers"].sum() == 1
    assert expected_churners(demo.portfolio) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# The campaign
# ---------------------------------------------------------------------------


def test_the_guardrail_breakdown_names_each_reason_in_plain_language(demo):
    rejections = guardrail_rejections(demo.decisions)
    assert set(rejections["code"]) == {"low_risk"}
    assert rejections.loc[0, "customers"] == 1
    assert "low churn risk" in rejections.loc[0, "reason"]


def test_campaign_totals_separate_review_states(demo):
    totals = campaign_totals(demo.decisions)
    assert totals["rows"] == 4
    assert (totals["approved"], totals["rejected"]) == (1, 1)
    assert totals["proposed"] == 1  # 0004 was excluded as low risk, so it is not pending
    assert totals["offers"] == 3


def test_only_unreviewed_proposals_are_pending(demo):
    pending = pending_proposals(demo.decisions)
    assert set(pending["subscriber_id"]) == {"NA"}


def test_a_bigger_budget_is_a_preview_and_never_touches_the_snapshot(demo):
    before = demo.campaign["snapshot"]["rows"]
    preview, comparison = budget_preview(demo.campaign, 10_000.0)
    assert len(preview) == 4
    assert not comparison.empty
    assert demo.campaign["snapshot"]["rows"] == before


def test_a_budget_of_zero_funds_nothing(demo):
    preview, _ = budget_preview(demo.campaign, 0.0)
    assert preview["recommended_offer_id"].eq(NO_OFFER).all()
    assert set(preview.loc[preview["decision_code"].eq("budget"), "subscriber_id"]) == {
        "0001",
        "0002",
        "NA",
    }


def test_the_offer_is_looked_up_in_the_catalogue(demo):
    offer = offer_row(demo, "SABAH_1")
    assert offer["price_lyd"] == 1
    assert offer["name_ar"]
    assert offer_row(demo, "NOT_A_PACKAGE") is None


def test_an_unreviewed_proposal_names_no_reviewer(demo):
    """It showed "reviewed by nan" on screen: pandas casts the empty name to text."""
    unreviewed = subscriber_view(demo, "NA")
    assert unreviewed["status"] == "proposed"
    assert unreviewed["reviewer"] is None
    assert unreviewed["reviewed_at"] is None

    reviewed = subscriber_view(demo, "0001")
    assert reviewed["reviewer"] == "Ali Marghem"


def test_the_paths_come_from_the_environment_when_it_names_them(tmp_path):
    defaults = DemoPaths.from_environment({})
    assert defaults == DemoPaths()

    chosen = DemoPaths.from_environment(
        {
            CAMPAIGN_DIR_VARIABLE: str(tmp_path / "campaign-002"),
            PORTFOLIO_VARIABLE: str(tmp_path / "other.csv"),
        }
    )
    assert chosen.campaign_dir == tmp_path / "campaign-002"
    assert chosen.campaign_path == tmp_path / "campaign-002" / "proposals.json"
    assert chosen.portfolio_path == tmp_path / "other.csv"
    assert chosen.bundle_dir == DemoPaths().bundle_dir  # untouched


# ---------------------------------------------------------------------------
# The customer message
# ---------------------------------------------------------------------------


def test_one_arabic_character_halves_the_sms_limit():
    """GSM-7 gives 160 per part; a single Arabic character forces UCS-2 and 70."""
    latin = sms_parts("A" * 100)
    assert (latin["encoding"], latin["limit"], latin["parts"]) == ("GSM-7", 160, 1)

    arabic = sms_parts("A" * 99 + "ن")
    assert (arabic["encoding"], arabic["limit"]) == ("UCS-2", 70)
    assert arabic["parts"] == 2  # the same length, billed twice


def test_a_short_arabic_message_is_one_part():
    parts = sms_parts(ARABIC)
    assert parts["encoding"] == "UCS-2"
    assert parts["parts"] == 1
    assert parts["remaining"] == 70 - len(ARABIC)


def test_a_long_arabic_message_is_counted_in_concatenated_parts():
    parts = sms_parts("ن" * 200)
    assert parts["parts"] == 3  # 200 / 67, rounded up
    assert parts["over_one_part"] is True


def test_the_message_names_the_package_and_the_reason(demo):
    subscriber = subscriber_view(demo, "0001")
    offer = offer_row(demo, subscriber["recommended_offer_id"])
    arabic = customer_message(subscriber, offer, "ar")
    english = customer_message(subscriber, offer, "en")
    assert offer["name_ar"] in arabic
    assert "06:00-11:00" in arabic
    assert offer["name_en"] in english
    assert "06:00-11:00" in english


def test_no_risk_or_value_figure_can_reach_the_customer(demo):
    """The customer is never told how likely the operator thinks they are to leave."""
    subscriber = subscriber_view(demo, "0001")
    offer = offer_row(demo, subscriber["recommended_offer_id"])
    for language in ("ar", "en"):
        message = customer_message(subscriber, offer, language)
        assert "0.5" not in message
        assert str(subscriber["value_12m_base_lyd"]) not in message
        for word in ("churn", "probability", "risk", "tier"):
            assert word not in message.lower()


def test_an_unknown_language_is_refused(demo):
    with pytest.raises(ValueError, match="Arabic or English"):
        customer_message({}, None, "fr")
