"""The proposal must agree with the configs it describes.

This file exists because of a real failure. When the smallest recharge card
changed from 3 to 5 LYD, the M4 argument was rewritten in section 6.4 and in
the pitch -- and silently left stale in section 1 and section 2.5, which are
the two places the argument is actually *made*. The configs were right and the
document was wrong in three places at once.

A proposal is a deliverable. Numbers in it are claims an evaluator will check
against the code, so they belong under test like any other contract.

Scope, deliberately narrow: only figures that are *derived from* a config value
are asserted here. Prose, framing and labelled estimates are not, because
pinning them would make the document unchangeable rather than consistent.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from cvm.config import load_conf

PROPOSAL = Path(__file__).resolve().parents[2] / "docs/proposal/AI_CVM_Suite_SIC_Proposal_v2.md"


@pytest.fixture(scope="module")
def doc() -> str:
    return PROPOSAL.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def money() -> dict[str, float]:
    """The handful of numbers everything else in the business case derives from."""
    market = load_conf("market")
    arpu = market["base"]["monthly_arpu_lyd"]
    return {
        "arpu": arpu,
        "annual": arpu * 12,
        "smallest_card": float(min(market["recharge"]["denominations_lyd"])),
        "data_advance": load_conf("catalogue")["emergency_credit"]["net_fi_waqtuh"]["price_lyd"],
        # From conf/market.yaml, not hardcoded here. A number the business case
        # turns on should have one home, and this file is not it.
        "blended_incentive": market["base"]["blended_incentive_lyd"],
        "treated": 120_000.0,
    }


# --- The M4 argument -------------------------------------------------------
# It is stated four times (sections 1, 2.5, 6.4 and the pitch) and must say the
# same thing in all four.


def test_the_advance_equals_the_smallest_card(money):
    """The finding rests on an EQUALITY. If a price moves, the prose is wrong."""
    assert money["data_advance"] == money["smallest_card"] == 5.0


def test_no_section_still_claims_the_debt_is_unclearable(doc):
    """The retired argument. A 3 LYD card could not clear a 5 LYD debt; a 5 LYD
    card can, which is why the claim is now a disincentive rather than a
    lockout. These phrases belonged to the old version."""
    for retired in ("cannot clear", "locked out", "unclearable"):
        assert retired not in doc, f"retired M4 claim resurfaced: {retired!r}"


def test_the_weaker_evidence_is_admitted(doc):
    """An exact equality is weaker than an impossibility. Saying so is the
    point -- an evaluator who spots it unprompted is a much worse outcome."""
    assert "weaker evidence than an impossibility" in doc


def test_the_airtime_asymmetry_is_recorded(doc):
    """1 and 3 LYD airtime advances leave change off the smallest card, so only
    the 5 LYD rung has the zero-residual problem. It is a design reason to
    prefer the small rungs and the document should carry it."""
    assert "Only the 5 LYD rung reproduces the" in doc
    rungs = load_conf("catalogue")["emergency_credit"]["rasid_fi_waqtuh"]["denominations_lyd"]
    assert [r for r in rungs if r < load_conf("market")["recharge"]["denominations_lyd"][0]] == [
        1,
        3,
    ]


# --- The economics ---------------------------------------------------------


def test_twelve_month_value_matches_arpu(money, doc):
    assert money["annual"] == 480.0
    assert "480 LYD" in doc


def test_break_even_uplift_is_quoted_correctly(money, doc):
    """cost / 12-month value. The decision engine, the business case and
    m3_uplift.yaml all turn on this one number."""
    breakeven = money["blended_incentive"] / money["annual"]
    assert breakeven * 100 == pytest.approx(1.04, abs=0.005)
    assert f"{money['blended_incentive']:.0f} / {money['annual']:.0f} = 1.04 pp" in doc


def test_clv_ceiling_matches_the_guardrail(money):
    fraction = load_conf("pricing")["guardrails"]["clv_ceiling"]["max_fraction_of_clv"]
    assert money["annual"] * fraction == 72.0


def test_headline_roi_is_arithmetic(money, doc):
    retained = money["treated"] * 0.025  # 2.5 pp uplift, the assumption in section 6
    cost = money["treated"] * money["blended_incentive"]
    assert retained * money["annual"] / cost == pytest.approx(2.4, abs=0.01)
    assert "ROI ≈ 2.4×" in doc  # noqa: RUF001 -- must match the document exactly


def test_the_roi_table_admits_a_loss_making_cell(doc):
    """At a 5 LYD incentive, 1 pp of uplift does not pay for itself. A
    sensitivity table with no losing cell is not a sensitivity table."""
    assert "**0.96×**" in doc  # noqa: RUF001 -- must match the document exactly


# --- Cannibalisation -------------------------------------------------------


def test_base_monthly_is_really_the_base(doc):
    """The structural exemption is only sound while 35 LYD is mid-ladder: a
    subscriber on it must have somewhere cheaper to have come from and
    somewhere dearer to fall from."""
    cann = load_conf("pricing")["guardrails"]["cannibalisation"]
    items = load_conf("catalogue")["families"]["monthly"]["items"]
    base = next(i for i in items if i["id"] == cann["base_monthly_offer_id"])
    prices = [i["price_lyd"] for i in items]

    assert base["price_lyd"] == cann["base_monthly_price_lyd"]
    assert min(prices) < base["price_lyd"] < max(prices)


@pytest.mark.parametrize(
    ("from_price", "expected_loss", "expected_share"),
    [(50, 14, "7.1%"), (80, 44, "2.3%")],
)
def test_downgrade_break_evens_are_quoted_correctly(
    money, doc, from_price: int, expected_loss: int, expected_share: str
):
    """The loss is the gap between rungs, not the whole bundle, because nobody
    drops below the base."""
    cat = load_conf("catalogue")
    cann = load_conf("pricing")["guardrails"]["cannibalisation"]
    morning = next(
        i["price_lyd"] for i in cat["families"]["morning_offpeak"]["items"] if i["id"] == "SABAH_1"
    )

    loss = from_price - (cann["base_monthly_price_lyd"] + morning)
    assert loss == expected_loss

    gain_per_month = money["treated"] * 0.025 * money["arpu"]
    share = (gain_per_month / loss) / money["treated"] * 100
    assert f"{share:.1f}%" == expected_share
    assert f"**{expected_share}**" in doc


def test_the_erosion_cap_sits_below_the_worst_case(money):
    """2% is chosen against the two-rung break-even, not the one-rung one. A cap
    tuned to the friendlier number would be the flattering choice."""
    cann = load_conf("pricing")["guardrails"]["cannibalisation"]
    cat = load_conf("catalogue")
    morning = next(
        i["price_lyd"] for i in cat["families"]["morning_offpeak"]["items"] if i["id"] == "SABAH_1"
    )
    worst_loss = 80 - (cann["base_monthly_price_lyd"] + morning)
    worst_break_even = (money["arpu"] * 0.025 / worst_loss) * 100

    assert cann["max_simulated_arpu_erosion"] * 100 < worst_break_even


# --- Scope claims ----------------------------------------------------------


def test_no_sequence_arm_survives_anywhere(doc):
    m1 = load_conf("models/m1_churn")
    assert "arm_b_lstm" not in m1
    assert "gradient_boosting" in m1
    for gone in ("LSTM", "Arm B", "free-tier GPU", "both arms"):
        assert gone not in doc, f"sequence-arm reference resurfaced: {gone!r}"


def test_the_sequence_arm_is_scoped_out_not_claimed_as_a_win(doc):
    """We did not benchmark a sequence model. Saying we beat one would be the
    easy lie, and it is the kind an evaluator can test."""
    assert "considered and scoped out" in doc
    assert "we do not claim to have beaten one" in doc


def test_validation_sources_are_named_as_the_thing_they_gate(doc):
    """Criteo, Hillstrom and Online Retail II each turn a claim about a method
    into a measurement of it. They were 'optional' once, which is how the
    strongest claim in the document nearly ended up unsupportable."""
    m3 = load_conf("models/m3_uplift")
    assert m3["validation"]["primary_source"] == "criteo_uplift"
    assert m3["validation"]["warmup_source"] == "hillstrom"
    assert "validation sources**" in doc
    assert "Deferring them is the most likely way" in doc


def test_kkbox_left_with_the_sequence_arm(doc):
    assert "KKBox" not in doc


# --- Document hygiene ------------------------------------------------------


def test_every_relative_link_resolves(doc):
    broken = [
        href
        for href in set(re.findall(r"\]\(([^)\s]+)\)", doc))
        if not href.startswith(("http", "#", "mailto:"))
        and not (PROPOSAL.parent / href.split("#")[0]).resolve().exists()
    ]
    assert not broken, f"broken links: {broken}"


def test_every_section_cross_reference_exists(doc):
    """A §6.2 that points at nothing is worse than no pointer."""
    missing = [
        ref
        for ref in sorted(set(re.findall(r"§(\d(?:\.\d)?)", doc)))
        if (f"### {ref}" if "." in ref else f"## {ref}") not in doc
    ]
    assert not missing, f"cross-references with no section: {missing}"
