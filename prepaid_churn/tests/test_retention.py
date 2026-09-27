import json
from copy import deepcopy
from dataclasses import asdict, replace

import numpy as np
import pandas as pd
import pytest

from prepaid_churn.bundle import save_bundle
from prepaid_churn.campaign import (
    build_campaign,
    campaign_rows,
    load_campaign,
    released_campaign,
    review_campaign,
    review_file,
    save_campaign,
)
from prepaid_churn.cli import main
from prepaid_churn.data import REPORTS_DIR
from prepaid_churn.operator_market import load_market, load_offers
from prepaid_churn.retention import (
    NO_OFFER,
    RetentionError,
    decision_inputs,
    fingerprint,
    holdout_mask,
    load_policy,
    propose,
    validate_policy,
)
from prepaid_churn.retention_report import decisions_report
from prepaid_churn.value import fit_tiers, save_tiers

STAMP = "2026-09-20T12:00:00+00:00"


@pytest.fixture
def offers():
    return load_offers()


@pytest.fixture
def policy():
    # The mechanism tests keep a preferred morning offer with a larger assumed share, so they
    # exercise the preference; the shipped policy assumes the same 5% for every offer (decision 46).
    return replace(load_policy(), holdout_fraction=0.0, offpeak_share_saved=0.10)


@pytest.fixture
def campaign(customers, offers, policy):
    decisions, comparison = propose(customers, offers, policy)
    return build_campaign(customers, decisions, comparison, offers, policy, STAMP)


def test_expected_value_and_cost_use_stated_assumptions(customers, offers, policy):
    result, _ = propose(customers, offers, policy)
    assert result["recommended_offer_id"].eq("SABAH_1").all()
    assert result["expected_cost_lyd"].eq(0.35).all()
    np.testing.assert_allclose(
        result["expected_net_value_lyd"],
        customers["churn_probability"] * policy.offpeak_share_saved * 100 - 0.35,
    )
    assert result["status"].eq("proposed").all()
    assert result["offer_reason_en"].str.contains("06:00-11:00").all()
    assert result["offer_reason_ar"].str.contains("06:00-11:00").all()


@pytest.mark.parametrize("budget,number", [(0, 0), (0.3499, 0), (0.35, 1), (0.7, 2)])
def test_greedy_budget_never_overspends(customers, offers, policy, budget, number):
    result, _ = propose(customers, offers, replace(policy, budget_lyd=budget))
    assert result["status"].eq("proposed").sum() == number
    assert result["expected_cost_lyd"].sum() <= budget
    assert result.iloc[:number]["status"].eq("proposed").all()


def test_low_risk_silent_unscored_and_nonpositive_get_no_offer(customers, offers, policy):
    customers.loc[0, "risk_band"] = "low"
    for index, band, status in [
        (1, "already_silent", "already_silent"),
        (2, "unavailable", "risk_unavailable"),
    ]:
        customers.loc[index, ["risk_band", "value_status"]] = [band, status]
        customers.loc[index, ["churn_probability", "value_12m_base_lyd"]] = np.nan
    customers.loc[3, "churn_probability"] = 0
    result, _ = propose(customers, offers, policy)
    assert result["decision_code"].tolist() == [
        "low_risk",
        "already_silent",
        "risk_unavailable",
        "nonpositive_value",
    ]
    assert result["recommended_offer_id"].eq(NO_OFFER).all()
    assert result["expected_cost_lyd"].eq(0).all()
    assert result["expected_net_value_lyd"].eq(0).all()


def test_customer_value_cap_is_enforced(customers, offers, policy):
    result, _ = propose(customers, offers, replace(policy, max_value_fraction=0.001))
    assert result["decision_code"].eq("no_eligible_offer").all()


def test_cannibalisation_guard_uses_held_monthly_bundle_even_at_high_risk(
    customers, offers, policy
):
    customers["bundle_held"] = ["MO_20", "MO_40", "MO_80", "DAY_HALF"]
    result, _ = propose(customers, offers, policy)
    assert result.loc[[0, 3], "recommended_offer_id"].eq("SABAH_1").all()
    assert result.loc[[1, 2], "recommended_offer_id"].eq("DAY_50MB").all()


def test_service_relevance_and_unknown_technical_eligibility(customers, offers, policy):
    # A voice-only customer above the base rung now has nothing to be offered.
    # The Mix families were the only metered data-and-voice packages, and Ali confirmed on
    # 2026-09-22 that they are no longer sold. What is left with voice is the Family share
    # tier, which the membership guard excludes, and the morning pass, which the
    # cannibalisation guard blocks above MO_20. No offer is the correct answer, not a bug.
    customers["uses_data"] = False
    customers["bundle_held"] = "MO_80"
    result, _ = propose(customers, offers, policy)
    assert result["recommended_offer_id"].eq(NO_OFFER).all()
    assert result["decision_code"].eq("no_eligible_offer").all()
    customers["uses_data"] = True
    excluded = offers[offers["network"].notna() | offers["members"].gt(1)]["offer_id"]
    # Make unknown-eligibility products economically dominant if the guard is removed.
    offers.loc[offers["offer_id"].isin(excluded), "price_lyd"] = 0.001
    result, _ = propose(customers, offers, replace(policy, offpeak_share_saved=0))
    assert not result["recommended_offer_id"].isin(excluded).any()
    customers[["uses_voice", "uses_data"]] = False
    result, _ = propose(customers, offers, policy)
    assert result["decision_code"].eq("no_eligible_offer").all()


def test_holdout_is_random_reproducible_and_independent_of_order():
    ids = pd.Series([f"test-{i}" for i in range(1000)])
    actual = holdout_mask(ids, 0.1, 42)
    assert 60 < actual.sum() < 140
    pd.testing.assert_series_equal(actual, holdout_mask(ids, 0.1, 42))
    pd.testing.assert_series_equal(actual, holdout_mask(ids.iloc[::-1], 0.1, 42).iloc[::-1])
    assert not actual.equals(holdout_mask(ids, 0.1, 43))
    assert holdout_mask(ids.iloc[[4]], 0.1, 42).iloc[0] == actual.iloc[4]


def test_holdout_never_receives_offer(customers, offers, policy):
    result, comparison = propose(customers, offers, replace(policy, holdout_fraction=1))
    assert result["decision_code"].eq("holdout").all()
    assert result["recommended_offer_id"].eq(NO_OFFER).all()
    assert comparison["expected_cost_lyd"].eq(0).all()


def test_row_order_does_not_change_budget_or_offer_ties(customers, offers, policy):
    customers["churn_probability"] = 0.5
    policy = replace(policy, budget_lyd=0.7)
    result, _ = propose(customers, offers, policy)
    shuffled, _ = propose(customers.iloc[::-1], offers.iloc[::-1], policy)
    pd.testing.assert_frame_equal(
        result.sort_values("subscriber_id").reset_index(drop=True),
        shuffled.sort_values("subscriber_id").reset_index(drop=True),
    )


def test_equal_spend_comparison_includes_untargeted_low_risk_and_matches_exactly(
    customers, offers, policy
):
    customers["churn_probability"] = [0.9, 0.2, 0.01, 0.02]
    customers["value_12m_base_lyd"] = [2.0, 100.0, 10.0, 10.0]
    customers.loc[[2, 3], "risk_band"] = "low"
    result, comparison = propose(customers, offers, replace(policy, budget_lyd=0.35))
    assert result.loc[1, "status"] == "proposed"
    assert comparison["expected_cost_lyd"].eq(0.35).all()
    assert comparison.loc[0, "assumed_net_value_lyd"] > comparison.loc[1, "assumed_net_value_lyd"]
    assert comparison.loc[0, "assumed_net_value_lyd"] > comparison.loc[2, "assumed_net_value_lyd"]
    assert comparison.loc[1, "expected_customers"] != int(comparison.loc[1, "expected_customers"])
    # Feasible bonuses cost 0.125, 0.350, 0.125, 0.125; their net values are below.
    assert comparison.loc[1, "assumed_net_value_lyd"] == pytest.approx(
        (-0.035 + 1.65 - 0.12 - 0.115) * 0.35 / 0.725
    )
    assert comparison.loc[2, "assumed_net_value_lyd"] == pytest.approx(
        -0.035 + (0.35 - 0.125) / 0.35 * 1.65
    )


@pytest.mark.parametrize(
    "field,bad",
    [
        ("budget_lyd", -1),
        ("budget_lyd", float("nan")),
        ("share_saved", 1.01),
        ("offpeak_share_saved", -0.01),
        ("seed", True),
        ("share_of_price_metered", 0),
        ("holdout_fraction", float("inf")),
    ],
)
def test_invalid_policy_is_rejected(policy, field, bad):
    with pytest.raises(RetentionError):
        validate_policy(replace(policy, **{field: bad}))


@pytest.mark.parametrize(
    "column,bad",
    [
        ("subscriber_id", ""),
        ("bundle_held", "unknown"),
        ("churn_probability", np.inf),
        ("churn_probability", -1.0),
        ("value_12m_base_lyd", np.nan),
        ("risk_band", "unavailable"),
    ],
)
def test_invalid_decision_inputs_fail_closed(customers, offers, policy, column, bad):
    customers.loc[0, column] = bad
    with pytest.raises(RetentionError):
        propose(customers, offers, policy)


def test_duplicate_ids_are_not_silently_allocated_twice(customers, offers, policy):
    customers.loc[1, "subscriber_id"] = customers.loc[0, "subscriber_id"]
    with pytest.raises(RetentionError, match="unique"):
        propose(customers, offers, policy)


def test_unapproved_or_rejected_rows_never_release(campaign):
    assert released_campaign(campaign).empty
    reviewed = review_campaign(campaign, "Reviewer One", subscriber_ids=["0001"], reviewed_at=STAMP)
    reviewed = review_campaign(
        reviewed, "Reviewer Two", "rejected", ["0002"], "Not suitable", STAMP
    )
    released = released_campaign(reviewed)
    assert released["subscriber_id"].tolist() == ["0001"]
    assert released["reviewer"].tolist() == ["Reviewer One"]
    assert "churn_probability" not in released and "expected_net_value_lyd" not in released
    assert len(reviewed["reviews"]) == 2
    assert reviewed["reviews"][1]["note"] == "Not suitable"
    assert campaign["reviews"] == []  # pure review function
    assert campaign_rows(reviewed)["status"].tolist() == [
        "approved",
        "rejected",
        "proposed",
        "proposed",
    ]


def test_whole_list_review_only_resolves_pending(campaign):
    first = review_campaign(campaign, "Reviewer", "rejected", ["0001"], reviewed_at=STAMP)
    all_pending = review_campaign(first, "Reviewer", reviewed_at=STAMP)
    assert len(released_campaign(all_pending)) == 3
    assert len(all_pending["reviews"]) == 4
    assert review_campaign(all_pending, "Reviewer")["reviews"] == all_pending["reviews"]


@pytest.mark.parametrize(
    "reviewer,ids", [(" ", None), ("Reviewer", ["missing"]), ("Reviewer", ["0001", "0001"])]
)
def test_invalid_review_is_atomic(campaign, reviewer, ids):
    with pytest.raises(RetentionError):
        review_campaign(campaign, reviewer, subscriber_ids=ids)
    assert campaign["reviews"] == []


def test_holdouts_and_no_offers_cannot_be_approved(customers, offers, policy):
    policy = replace(policy, holdout_fraction=1)
    rows, comparison = propose(customers, offers, policy)
    campaign = build_campaign(customers, rows, comparison, offers, policy)
    with pytest.raises(RetentionError, match="pending"):
        review_campaign(campaign, "Reviewer", subscriber_ids=["0001"])


def test_review_cannot_be_repeated_or_backdated_without_timezone(campaign):
    reviewed = review_campaign(campaign, "Reviewer", subscriber_ids=["0001"], reviewed_at=STAMP)
    with pytest.raises(RetentionError, match="pending"):
        review_campaign(reviewed, "Reviewer", subscriber_ids=["0001"])
    with pytest.raises(RetentionError, match="UTC"):
        review_campaign(campaign, "Reviewer", reviewed_at="2026-09-20T12:00")


def test_files_preserve_ids_reviews_and_approved_only_release(campaign, tmp_path):
    path = save_campaign(campaign, tmp_path / "campaign")
    assert pd.read_csv(path.parent / "released.csv").empty
    review_file(path, "Reviewer", subscriber_ids=["0001", "NA"], note="Reviewed in person")
    assert pd.read_csv(
        path.parent / "released.csv", keep_default_na=False, dtype={"subscriber_id": str}
    )["subscriber_id"].tolist() == ["0001", "NA"]
    loaded = load_campaign(path)
    assert len(loaded["reviews"]) == 2
    events = [
        json.loads(line)
        for line in (path.parent / "review_log.jsonl").read_text("utf-8").splitlines()
    ]
    assert events == loaded["reviews"]
    assert loaded["snapshot"] == campaign["snapshot"]
    with pytest.raises(RetentionError, match="already exists"):
        save_campaign(campaign, path.parent)


def test_tampered_proposals_fail_and_csv_edits_cannot_approve(campaign, tmp_path):
    path = save_campaign(campaign, tmp_path / "campaign")
    (path.parent / "decisions.csv").write_text("status\napproved\n", encoding="utf-8")
    assert released_campaign(load_campaign(path)).empty
    with pytest.raises(RetentionError, match="JSON|proposals.json"):
        review_file(path.parent / "decisions.csv", "Reviewer")
    changed = deepcopy(campaign)
    changed["snapshot"]["rows"][0]["expected_cost_lyd"] = 0.001
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(RetentionError, match="checksum"):
        review_file(path, "Reviewer")
    assert pd.read_csv(path.parent / "released.csv").empty


def test_fake_review_for_another_campaign_is_rejected(campaign):
    reviewed = review_campaign(campaign, "Reviewer", reviewed_at=STAMP)
    reviewed["reviews"][0]["campaign_id"] = "another-campaign"
    with pytest.raises(RetentionError, match="another snapshot"):
        released_campaign(reviewed)


def test_snapshot_cannot_claim_direct_approval(campaign):
    campaign["snapshot"]["rows"][0]["status"] = "approved"
    campaign["campaign_id"] = fingerprint(campaign["snapshot"])
    with pytest.raises(RetentionError, match="reviewed status"):
        released_campaign(campaign)


def test_review_lock_prevents_lost_updates(campaign, tmp_path):
    path = save_campaign(campaign, tmp_path / "campaign")
    (path.parent / ".review.lock").write_text("", encoding="utf-8")
    with pytest.raises(RetentionError, match="Another review"):
        review_file(path, "Reviewer")
    assert load_campaign(path)["reviews"] == []


def test_report_states_assumptions_and_equal_spend(customers, offers, policy):
    result, comparison = propose(customers, offers, policy)
    report = decisions_report(result, comparison, offers, policy)
    for name in asdict(policy):
        assert name in report
    assert "fractional last inclusion" in report
    assert "not an experimentally measured benefit" in report
    assert "not a cumulative annual" in report
    assert "favours it by construction" in report  # the comparison cannot prove targeting
    assert "greedy" in report  # and the picking is not an optimum either
    assert "permanent control group" in report  # the same seed holds out the same customers
    proposed = result["status"].eq("proposed")
    assert ("not from measured response" in report) == bool(proposed.any())


def test_the_shipped_policy_assumes_the_same_share_for_every_offer(customers, offers):
    """With one share for every offer, net value differs only by cost (decision 46)."""
    shipped = replace(load_policy(), holdout_fraction=0.0)
    assert shipped.share_saved == shipped.offpeak_share_saved == 0.05
    result, comparison = propose(customers, offers, shipped)
    report = decisions_report(result, comparison, offers, shipped)
    assert "the same share of churners" in report
    assert "not from measured response" not in report


def test_live_input_path_uses_frozen_tier_rate_and_existing_bundle(raw, trained, bundle, offers):
    model = fit_tiers(trained["datasets"]["train"], load_market())
    inputs = decision_inputs(raw, model, bundle, offers)
    assert inputs["value_status"].tolist() == [
        "scenario",
        "already_silent",
        "scenario",
        "already_silent",
    ]
    assert inputs["bundle_held"].isin(["PAYG", *offers["offer_id"]]).all()
    no_risk = decision_inputs(raw, model, None, offers)
    rows, _ = propose(no_risk, offers, load_policy())
    assert rows["recommended_offer_id"].eq(NO_OFFER).all()


def test_decide_and_approve_cli(raw, trained, bundle, tmp_path):
    model = fit_tiers(trained["datasets"]["train"], load_market())
    model_path, input_path = tmp_path / "tiers.json", tmp_path / "export.csv"
    save_tiers(model, model_path)
    save_bundle(bundle, tmp_path / "bundle")
    raw.to_csv(input_path, index=False)
    directory = tmp_path / "campaign"
    main(
        [
            "decide",
            "--input",
            str(input_path),
            "--model",
            str(model_path),
            "--bundle",
            str(tmp_path / "bundle"),
            "--output-dir",
            str(directory),
            "--report",
            str(tmp_path / "report.md"),
        ]
    )
    assert pd.read_csv(directory / "released.csv").empty
    main(
        ["approve", "--proposals", str(directory / "proposals.json"), "--reviewer", "Test Reviewer"]
    )
    campaign = load_campaign(directory / "proposals.json")
    assert all(event["reviewer"] == "Test Reviewer" for event in campaign["reviews"])
    assert len(released_campaign(campaign)) == sum(
        row["status"] == "proposed" for row in campaign["snapshot"]["rows"]
    )


def test_the_decision_report_defaults_beside_the_campaign(raw, trained, bundle, tmp_path):
    """Running the documented command must not overwrite the committed readiness report.

    Every run needs a new output directory and may use a different budget, so a fixed
    default under reports/ meant `churn decide` left a tracked file dirty.
    """
    committed = REPORTS_DIR / "decisions.md"
    before = committed.read_text(encoding="utf-8")

    model = fit_tiers(trained["datasets"]["train"], load_market())
    model_path, input_path = tmp_path / "tiers.json", tmp_path / "export.csv"
    save_tiers(model, model_path)
    save_bundle(bundle, tmp_path / "bundle")
    raw.to_csv(input_path, index=False)
    directory = tmp_path / "campaign"
    main(
        [
            "decide",
            "--input",
            str(input_path),
            "--model",
            str(model_path),
            "--bundle",
            str(tmp_path / "bundle"),
            "--output-dir",
            str(directory),
        ]
    )
    assert (directory / "decisions.md").exists()
    assert committed.read_text(encoding="utf-8") == before


def test_approval_cli_selects_and_rejects_individual_proposals(campaign, tmp_path):
    path = save_campaign(campaign, tmp_path / "campaign")
    main(
        [
            "approve",
            "--proposals",
            str(path),
            "--reviewer",
            "Named Reviewer",
            "--subscriber-id",
            "0001",
            "--note",
            "Accepted",
        ]
    )
    main(
        [
            "approve",
            "--proposals",
            str(path),
            "--reviewer",
            "Named Reviewer",
            "--subscriber-id",
            "0002",
            "--reject",
            "--note",
            "Declined",
        ]
    )
    reviewed = load_campaign(path)
    assert released_campaign(reviewed)["subscriber_id"].tolist() == ["0001"]
    assert [event["decision"] for event in reviewed["reviews"]] == ["approved", "rejected"]
    assert [event["note"] for event in reviewed["reviews"]] == ["Accepted", "Declined"]


def test_interrupted_release_can_be_recovered_without_duplicate_reviews(
    campaign, tmp_path, monkeypatch
):
    from prepaid_churn import campaign as storage

    path = save_campaign(campaign, tmp_path / "campaign")
    original = storage._atomic_text

    def fail_release(target, text):
        if target.name == "released.csv":
            raise OSError("simulated write interruption")
        original(target, text)

    monkeypatch.setattr(storage, "_atomic_text", fail_release)
    with pytest.raises(OSError, match="interruption"):
        review_file(path, "Named Reviewer", subscriber_ids=["0001"])
    assert pd.read_csv(path.parent / "released.csv").empty
    assert len(load_campaign(path)["reviews"]) == 1
    monkeypatch.setattr(storage, "_atomic_text", original)
    main(["approve", "--proposals", str(path), "--reviewer", "Named Reviewer", "--refresh"])
    recovered = load_campaign(path)
    assert len(recovered["reviews"]) == 1
    assert len(pd.read_csv(path.parent / "released.csv")) == 1
    assert campaign_rows(recovered)["status"].eq("proposed").sum() == 3


def test_empty_campaign_is_safe(customers, offers, policy):
    customers = customers.iloc[:0]
    rows, comparison = propose(customers, offers, policy)
    assert rows.empty
    assert comparison["expected_cost_lyd"].eq(0).all()
    campaign = build_campaign(customers, rows, comparison, offers, policy)
    assert released_campaign(review_campaign(campaign, "Reviewer")).empty
