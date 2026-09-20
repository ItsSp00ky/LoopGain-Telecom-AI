from copy import deepcopy

import numpy as np
import pandas as pd
import pytest
from conftest import build_population

from prepaid_churn.almadar import (
    PAY_AS_YOU_GO,
    STATUSES,
    VIEW_COLUMNS,
    InvalidCatalogueError,
    almadar_view,
    bundle_held,
    check_against_source,
    load_market,
    load_offers,
    lyd_rate,
    nearest_card,
    validate_market,
    validate_offers,
    view_report,
)
from prepaid_churn.cli import main
from prepaid_churn.windows import WINDOW_A, WINDOW_B, active_in_current_month

MARKET = {
    "arpu": {"monthly_lyd": 40.0, "status": "assumption", "source": "test"},
    "reference_spend": {"mean_monthly_recharge": 500.0, "status": "measured", "source": "test"},
    "recharge_cards": {"values_lyd": [5, 10, 20, 40, 100], "status": "reported", "source": "test"},
}


@pytest.fixture
def two_offers() -> pd.DataFrame:
    """A metered bundle and the morning pass, as they appear in offers.csv."""
    common = {
        "operator": "Almadar Aljadid",
        "network": None,
        "voice_minutes": None,
        "members": None,
        "max_download_mbps": None,
        "max_upload_mbps": None,
        "source_file": "source/internet_offers_data_v4.csv",
        "collected": "2026-09-18",
        "notes": None,
    }
    return pd.DataFrame(
        [
            common
            | {
                "offer_id": "MO_20",
                "family_ar": "عروض شهرية",
                "family_en": "Monthly offers",
                "name_ar": "نت 20",
                "name_en": "Net 20",
                "price_lyd": 35,
                "validity_ar": "30 يوم",
                "validity_hours": 720,
                "data_gb": 20,
                "data_unlimited": 0,
                "volume_source": "name",
                "voice_unlimited": 0,
                "valid_from_hour": None,
                "valid_to_hour": None,
                "source_row": 11,
            },
            common
            | {
                "offer_id": "SABAH_1",
                "family_ar": "عروض الصبح",
                "family_en": "Morning offers",
                "name_ar": "الصبح",
                "name_en": "Morning",
                "price_lyd": 1,
                "validity_ar": "صلاحية 1 يوم",
                "validity_hours": 24,
                "data_gb": None,
                "data_unlimited": 1,
                "volume_source": "stated",
                "voice_unlimited": 1,
                "valid_from_hour": 6,
                "valid_to_hour": 11,
                "source_row": 57,
            },
        ]
    )


def _problems(offers: pd.DataFrame) -> str:
    with pytest.raises(InvalidCatalogueError) as error:
        validate_offers(offers)
    return str(error.value)


def test_valid_offers_pass(two_offers):
    assert len(validate_offers(two_offers)) == 2


def test_every_broken_rule_is_reported_at_once(two_offers):
    broken = pd.concat([two_offers, two_offers.iloc[[0]]], ignore_index=True)
    broken.loc[1, "price_lyd"] = -1
    broken.loc[1, "data_gb"] = 5  # unlimited data with a volume
    broken.loc[1, "valid_to_hour"] = None  # half a time window
    broken.loc[2, "operator"] = "Unknown Telecom"
    problems = _problems(broken)
    for expected in (
        "offer_id",
        "price_lyd",
        "operator",
        "unlimited data has no volume",
        "a time window has both a start and an end",
    ):
        assert expected in problems


def test_volume_source_must_match_the_volume(two_offers):
    two_offers.loc[0, "data_gb"] = None  # "name" but no number
    problems = _problems(two_offers)
    assert "a volume read from the name is a number" in problems
    assert "volume source is 'none'" in problems


def test_unlimited_voice_has_no_minutes(two_offers):
    two_offers.loc[1, "voice_minutes"] = 100
    assert "unlimited voice has no minute count" in _problems(two_offers)


def test_extra_columns_are_refused(two_offers):
    # The catalogue is shared with the chatbot, so its columns are fixed.
    assert "cost" in _problems(two_offers.assign(cost=1.0))


def test_real_catalogue_is_valid_and_complete():
    offers = load_offers()
    assert len(offers) == 57
    assert offers["family_en"].nunique() == 17
    assert offers[["source_file", "source_row", "collected"]].notna().all().all()


def test_real_catalogue_matches_the_operator_file():
    assert check_against_source(load_offers()) == []


def test_ali_catalogue_is_the_catalogue_without_mix():
    # Ali_Branch kept 37 packages in 12 families; the 20 Mix packages are the difference.
    offers = load_offers()
    without_mix = offers[~offers["offer_id"].str.startswith("MIX_")]
    assert len(without_mix) == 37
    assert without_mix["family_en"].nunique() == 12


def test_a_changed_price_is_caught():
    offers = load_offers()
    offers.loc[offers["offer_id"] == "MO_20", "price_lyd"] = 30.0
    assert check_against_source(offers) == ["MO_20: price_lyd is 30.0, source says 35.0"]


def test_a_stated_volume_must_be_marked_stated():
    offers = load_offers()
    offers.loc[offers["offer_id"] == "MIX_DIA_1", "volume_source"] = "name"
    assert check_against_source(offers) == [
        "MIX_DIA_1: the source states the volume (3.0), so volume_source must be 'stated'"
    ]


def test_missing_and_repeated_source_rows_are_caught():
    offers = load_offers()
    offers.loc[offers["offer_id"] == "SABAH_1", "source_row"] = 56
    assert check_against_source(offers) == [
        "source/internet_offers_data_v4.csv: source rows missing [57], repeated [56], unknown []"
    ]


def test_real_market_facts_have_status_and_source():
    facts = load_market()
    assert all(table["status"] in STATUSES for table in facts.values())
    assert facts["recharge_cards"]["values_lyd"] == [5, 10, 20, 40, 100]
    assert facts["arpu"]["status"] == "assumption"


def test_market_facts_without_status_or_source_fail():
    with pytest.raises(InvalidCatalogueError) as error:
        validate_market({"arpu": {"monthly_lyd": 40.0}, "cards": [5, 10]})
    message = str(error.value)
    assert "arpu: status must be one of" in message
    assert "arpu: source is missing" in message
    assert "cards: must be a table" in message


def test_lyd_rate_makes_the_reference_customer_spend_the_arpu():
    assert lyd_rate(MARKET) == 0.08
    facts = load_market()
    reference = facts["reference_spend"]["mean_monthly_recharge"]
    assert reference * lyd_rate(facts) == pytest.approx(facts["arpu"]["monthly_lyd"])


def test_nearest_card():
    amounts = pd.Series([1, 7.4, 7.6, 15, 30, 150, np.nan])
    cards = nearest_card(amounts, [5, 10, 20, 40, 100])
    assert cards.iloc[:6].tolist() == [5, 5, 10, 10, 20, 100]  # a tie goes to the smaller card
    assert np.isnan(cards.iloc[6])


def test_bundle_held_follows_the_packs_of_the_current_month():
    zero = [0] * 5
    frame = pd.DataFrame(
        {
            "cur_monthly_2g": [0, 1, 0, 0, 0],
            "cur_monthly_3g": [1, 0, 0, 0, 1],
            "cur_sachet_2g": [0, 0, 2, 0, 0],
            "cur_sachet_3g": zero,
            "cur_total_rech_data": [2, 1, 2, 0, 5],
            "cur_av_rech_amt_data": [250, 100, 20, 0, 2500],
        }
    )
    held = bundle_held(frame, rate=0.08, offers=load_offers())
    assert held.tolist() == [
        "MO_20",  # 2 x 20 LYD of data: Net 20 (35 LYD) is the dearest monthly bundle it pays
        "MO_6",  # 8 LYD pays for no monthly bundle, so the cheapest one
        "DAY_100MB",  # short packs of 1.6 LYD: the 1 LYD daily pack
        PAY_AS_YOU_GO,
        "MO_80",
    ]


def test_view_reads_only_the_window_months(raw):
    from prepaid_churn.clean import clean
    from prepaid_churn.schema import validate

    before = almadar_view(clean(validate(raw)), WINDOW_A, MARKET, load_offers())
    changed = raw.copy()
    for column in ("total_rech_amt_8", "max_rech_amt_8", "monthly_3g_8", "sachet_2g_8"):
        changed[column] = changed[column] + 7
    after = almadar_view(clean(validate(changed)), WINDOW_A, MARKET, load_offers())
    assert list(before.columns) == list(VIEW_COLUMNS)
    pd.testing.assert_frame_equal(before, after)


def test_one_customer_alone_is_viewed_like_inside_the_batch():
    population = build_population()
    whole = almadar_view(population, WINDOW_B, MARKET, load_offers())
    alone = almadar_view(population.iloc[[0]], WINDOW_B, MARKET, load_offers())
    pd.testing.assert_frame_equal(alone, whole.iloc[[0]])


def test_view_report_states_every_assumption():
    population = build_population()
    view = almadar_view(population, WINDOW_B, MARKET, load_offers())
    report = view_report(view, active_in_current_month(population, WINDOW_B), MARKET, "x.csv")
    for expected in ("Almadar ARPU", "| assumption |", "| measured |", "| reported |", "PAYG"):
        assert expected in report


def test_almadar_view_command(raw, tmp_path):
    source, output, report = tmp_path / "export.csv", tmp_path / "view.csv", tmp_path / "r.md"
    raw.to_csv(source, index=False)
    main(["almadar-view", "--input", str(source), "--output", str(output), "--report", str(report)])
    assert len(pd.read_csv(output)) == len(raw)
    assert report.read_text(encoding="utf-8").startswith("# T18 Almadar view")


@pytest.mark.parametrize("value", [0, -1, np.inf, np.nan, "500", True])
def test_invalid_currency_scale_is_rejected(value):
    market = deepcopy(MARKET)
    market["reference_spend"]["mean_monthly_recharge"] = value
    with pytest.raises(InvalidCatalogueError, match="reference_spend"):
        lyd_rate(market)


@pytest.mark.parametrize("cards", [[], [0, 5], [np.inf], ["5"]])
def test_invalid_recharge_cards_are_rejected(cards):
    with pytest.raises(InvalidCatalogueError, match="recharge cards"):
        nearest_card(pd.Series([10.0]), cards)


def test_missing_offer_family_has_a_clear_error():
    from prepaid_churn.windows import window_features

    frame = window_features(build_population(), WINDOW_B)
    offers = load_offers()
    with pytest.raises(InvalidCatalogueError, match="monthly and daily"):
        bundle_held(frame, 0.08, offers[offers["family_en"] != "Daily offers"])
