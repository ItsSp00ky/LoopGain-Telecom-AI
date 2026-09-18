"""Layer 5 guardrails -- the commercial and ethical core.  Owner: E4 (+E6 review)

Six constraints from conf/pricing.yaml, enforced here and asserted in
tests/guardrails/. Every one of them is on the "never cut" list.

Design notes worth knowing before you change anything in this file:

* Guardrails **re-check the final number**. They do not trust the pricing
  function to have applied them, because a guardrail that only runs inside the
  thing it constrains is not a guardrail.
* A breach raises. It does not clamp silently and it does not warn. A
  loss-making offer that quietly became a break-even offer is an audit problem;
  a loud failure is a bug report.
* Every check returns an :class:`AppliedConstraint` recording whether it
  actually *bound*, not merely whether it passed. Knowing which constraint bound
  is what makes a decision explainable to a CFO and replayable from the log.

The functions here are pure: inputs in, verdict out, no I/O. That is what lets
the guardrail test suite run in CI without a feature store.
"""

from __future__ import annotations

from dataclasses import dataclass

from cvm.config import guardrail, load_conf


# N818 wants an `Error` suffix. A *breach* is the domain term here: it is the
# word used in the proposal, in the tests and in docs/INTEGRATION.md, and it
# says something a generic suffix does not -- a commitment was crossed, not
# merely that something failed. Keeping the name is the deliberate choice.
class GuardrailBreach(Exception):  # noqa: N818
    """A decision violated a constraint. Never caught to "just continue"."""


@dataclass(frozen=True)
class Verdict:
    """Outcome of one guardrail check."""

    name: str
    passed: bool
    binding: bool
    detail: str

    def raise_if_failed(self) -> None:
        if not self.passed:
            raise GuardrailBreach(f"{self.name}: {self.detail}")


# ---------------------------------------------------------------------------
# 1. Margin floor -- no loss-making offer, ever.
#    P(i,b) >= variable_cost(b) * (1 + min_margin)
# ---------------------------------------------------------------------------


def check_margin_floor(price_lyd: float, variable_cost_lyd: float) -> Verdict:
    """Assert the offered price clears variable cost plus the minimum margin."""
    min_margin = guardrail("pricing", "guardrails", "margin_floor", "min_margin")
    floor = variable_cost_lyd * (1.0 + min_margin)
    passed = price_lyd >= floor - 1e-9
    # "Binding" means the price sits at the floor: the margin rule, not the
    # discount formula, is what set this number.
    binding = passed and abs(price_lyd - floor) < 0.01
    return Verdict(
        name="margin_floor",
        passed=passed,
        binding=binding,
        detail=(
            f"price {price_lyd:.3f} LYD vs floor {floor:.3f} LYD "
            f"(cost {variable_cost_lyd:.3f} x {1 + min_margin:.2f})"
        ),
    )


def max_discount_within_margin(base_price_lyd: float, variable_cost_lyd: float) -> float:
    """The largest discount fraction that still clears the margin floor.

    Use this to clamp *before* pricing rather than discovering a breach after.
    """
    min_margin = guardrail("pricing", "guardrails", "margin_floor", "min_margin")
    floor = variable_cost_lyd * (1.0 + min_margin)
    if base_price_lyd <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - floor / base_price_lyd))


# ---------------------------------------------------------------------------
# 2. CLV ceiling -- the constraint that makes this defensible to a CFO.
# ---------------------------------------------------------------------------


def check_clv_ceiling(
    discount_cost_lyd: float,
    cumulative_spend_lyd_12m: float,
    predicted_clv_lyd: float,
) -> Verdict:
    """Assert cumulative 12-month retention spend stays within its CLV fraction.

    ``cumulative_spend_lyd_12m`` is what has *already* been spent on this
    subscriber in the trailing 12 months. Checking only the current offer is the
    classic way this constraint gets defeated: twelve small offers, each
    individually fine.
    """
    max_fraction = guardrail("pricing", "guardrails", "clv_ceiling", "max_fraction_of_clv")
    ceiling = max(0.0, predicted_clv_lyd) * max_fraction
    total = cumulative_spend_lyd_12m + discount_cost_lyd
    passed = total <= ceiling + 1e-9
    headroom = ceiling - cumulative_spend_lyd_12m
    binding = passed and discount_cost_lyd >= headroom - 0.01
    return Verdict(
        name="clv_ceiling",
        passed=passed,
        binding=binding,
        detail=(
            f"cumulative {total:.2f} LYD vs ceiling {ceiling:.2f} LYD "
            f"({max_fraction:.0%} of CLV {predicted_clv_lyd:.2f})"
        ),
    )


def clv_headroom(cumulative_spend_lyd_12m: float, predicted_clv_lyd: float) -> float:
    """LYD still available to spend on this subscriber this year."""
    max_fraction = guardrail("pricing", "guardrails", "clv_ceiling", "max_fraction_of_clv")
    return max(0.0, max(0.0, predicted_clv_lyd) * max_fraction - cumulative_spend_lyd_12m)


# ---------------------------------------------------------------------------
# 3. Budget constraint -- cohort allocation, solved in decision/budget_lp.py.
#    This is the post-hoc assertion that the solver respected its budget.
# ---------------------------------------------------------------------------


def check_budget(allocated_cost_lyd: float, budget_lyd: float) -> Verdict:
    passed = allocated_cost_lyd <= budget_lyd + 1e-6
    binding = passed and allocated_cost_lyd >= budget_lyd * 0.995
    return Verdict(
        name="budget",
        passed=passed,
        binding=binding,
        detail=f"allocated {allocated_cost_lyd:.2f} LYD vs budget {budget_lyd:.2f} LYD",
    )


# ---------------------------------------------------------------------------
# 4. Cannibalisation guard -- the most important commercial critique, answered.
# ---------------------------------------------------------------------------


def check_cannibalisation(
    churn_probability: float,
    value_decile: int,
    peak_usage_would_shift: bool = False,
    current_monthly_bundle_lyd: float | None = None,
) -> Verdict:
    """Exclude subscribers who would have paid full price.

    THE EXPOSURE IS THE LADDER, NOT THE PRODUCT. نت 20 at 35 LYD is the BASE
    monthly bundle -- what a subscriber needs to have data outside 06:00-11:00
    at all. A free morning does not remove that need, so the base is not
    substitutable and someone sitting on it has nowhere to fall. The risk is
    confined to subscribers ABOVE the base, who can use the pass to justify
    stepping down a rung.

    ``current_monthly_bundle_lyd`` is therefore the primary input:

        None or <= base   structurally immune -- pass
        > base            exposed -- apply the risk/value filter below

    Passing None (no monthly bundle held) is the common case for a pure PAYG
    or daily-pack subscriber, and it is a pass for the same reason: there is no
    bundle to downgrade from.

    ``peak_usage_would_shift`` comes from the simulated margin check in
    decision/offpeak.py -- the pass must be additive, not substitutable. It
    applies regardless of bundle, because shifting paid usage within the day
    is a different mechanism from stepping down the ladder.
    """
    conf = load_conf("pricing")["guardrails"]["cannibalisation"]

    if peak_usage_would_shift and conf.get("require_additive_offpeak_pack", True):
        return Verdict(
            "cannibalisation",
            passed=False,
            binding=True,
            detail="excluded: peak usage would shift rather than grow (not additive)",
        )

    base_lyd = float(conf["base_monthly_price_lyd"])
    if conf.get("exempt_at_or_below_base_monthly", True) and (
        current_monthly_bundle_lyd is None or current_monthly_bundle_lyd <= base_lyd
    ):
        held = (
            "no monthly bundle"
            if current_monthly_bundle_lyd is None
            else f"{current_monthly_bundle_lyd:.0f} LYD monthly"
        )
        return Verdict(
            "cannibalisation",
            passed=True,
            binding=False,
            detail=(
                f"structurally immune: {held} is at or below the "
                f"{base_lyd:.0f} LYD base -- no rung to fall to"
            ),
        )

    low_risk = churn_probability < conf["exclude_if_churn_prob_below"]
    high_value = value_decile > conf["exclude_if_value_decile_above"]

    if low_risk and high_value:
        return Verdict(
            "cannibalisation",
            passed=False,
            binding=True,
            detail=(
                f"excluded: churn {churn_probability:.3f} below "
                f"{conf['exclude_if_churn_prob_below']} and value decile "
                f"{value_decile} above {conf['exclude_if_value_decile_above']} "
                f"-- above the {base_lyd:.0f} LYD base and would have paid full price"
            ),
        )
    return Verdict(
        "cannibalisation",
        passed=True,
        binding=False,
        detail=f"eligible: above the {base_lyd:.0f} LYD base but exposure is acceptable",
    )


# ---------------------------------------------------------------------------
# 5. Fairness -- no pricing on protected or proxy-protected attributes.
# ---------------------------------------------------------------------------


def check_fairness(pricing_features: list[str]) -> Verdict:
    """Assert no forbidden attribute reached the pricing computation.

    Age group may inform offer *relevance*, never price. ``district`` stays on
    the forbidden list although this branch no longer models geography, so
    that reintroducing it later cannot silently make it a price lever.
    """
    forbidden = set(guardrail("pricing", "guardrails", "fairness", "forbidden_pricing_features"))
    used = forbidden.intersection(pricing_features)
    if used:
        return Verdict(
            "fairness",
            passed=False,
            binding=True,
            detail=(
                f"forbidden pricing features present: {sorted(used)}. "
                "District is a network-quality input only; age group may inform "
                "relevance, never price."
            ),
        )
    return Verdict("fairness", passed=True, binding=False, detail="no protected attributes used")


def audit_distribution(mean_discount_by_group: dict[str, float], dimension: str) -> Verdict:
    """Post-hoc audit: is discount spend distributed defensibly across a group?

    Replaces the redlining audit, which went with geography -- auditing a
    dimension we no longer model would have been theatre. ``dimension`` is
    ``value_decile`` or ``tenure_band``.

    **A gap here is expected and legitimate.** Loyalty tiers exist and d_max
    rises with tenure by design, so Platinum should receive more than Bronze.
    What this catches is a gap LARGER than the published tier structure
    explains, which is the signal that something other than the ladder is
    driving price.

    Run after every campaign allocation, not once at the end of the project.
    """
    conf = load_conf("pricing")["guardrails"]["fairness"]["distribution_audit"]
    allowed = conf["across"]
    if dimension not in allowed:
        raise ValueError(f"{dimension!r} is not an audited dimension. Allowed: {allowed}")

    max_gap = conf["max_mean_discount_gap"]
    if not mean_discount_by_group:
        return Verdict(
            "fairness", passed=True, binding=False, detail=f"no {dimension} groups to audit"
        )

    values = list(mean_discount_by_group.values())
    gap = max(values) - min(values)
    passed = gap <= max_gap + 1e-9
    hi = max(mean_discount_by_group, key=mean_discount_by_group.get)
    lo = min(mean_discount_by_group, key=mean_discount_by_group.get)
    return Verdict(
        "fairness",
        passed=passed,
        binding=not passed,
        detail=(f"{dimension} discount gap {gap:.4f} ({hi} vs {lo}) against limit {max_gap}"),
    )


# ---------------------------------------------------------------------------
# 6. Tier ceiling -- d_max by loyalty tier.
# ---------------------------------------------------------------------------


def tier_max_discount(tier: str) -> float:
    """``d_max`` for a loyalty tier, from conf/pricing.yaml."""
    tiers = load_conf("pricing")["tiers"]
    if tier not in tiers:
        raise KeyError(f"Unknown tier {tier!r}. Known: {sorted(tiers)}")
    return float(tiers[tier]["d_max"])


def check_tier_ceiling(discount_pct: float, tier: str) -> Verdict:
    d_max = tier_max_discount(tier)
    passed = discount_pct <= d_max + 1e-9
    binding = passed and abs(discount_pct - d_max) < 1e-4
    return Verdict(
        "tier_d_max",
        passed=passed,
        binding=binding,
        detail=f"discount {discount_pct:.3f} vs {tier} d_max {d_max:.3f}",
    )


# ---------------------------------------------------------------------------
# Composite: run every applicable guardrail over one candidate offer.
# ---------------------------------------------------------------------------


def evaluate_offer(
    *,
    price_lyd: float,
    base_price_lyd: float,
    variable_cost_lyd: float,
    discount_pct: float,
    tier: str,
    churn_probability: float,
    value_decile: int,
    predicted_clv_lyd: float,
    cumulative_spend_lyd_12m: float = 0.0,
    pricing_features: list[str] | None = None,
    peak_usage_would_shift: bool = False,
    current_monthly_bundle_lyd: float | None = None,
    raise_on_breach: bool = True,
) -> list[Verdict]:
    """Run all six guardrails over a candidate offer.

    Returns every verdict, in a fixed order, so the decision log records which
    constraints were *considered* as well as which bound. Raises on the first
    breach unless ``raise_on_breach`` is False -- which only the campaign
    simulator should do, so it can report how many candidates a constraint
    rejects.
    """
    discount_cost = max(0.0, base_price_lyd - price_lyd)
    verdicts = [
        check_margin_floor(price_lyd, variable_cost_lyd),
        check_tier_ceiling(discount_pct, tier),
        check_clv_ceiling(discount_cost, cumulative_spend_lyd_12m, predicted_clv_lyd),
        check_cannibalisation(
            churn_probability,
            value_decile,
            peak_usage_would_shift,
            current_monthly_bundle_lyd,
        ),
        check_fairness(pricing_features or []),
    ]
    if raise_on_breach:
        for v in verdicts:
            v.raise_if_failed()
    return verdicts
