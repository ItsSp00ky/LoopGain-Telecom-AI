"""M4 -- the learned advance limit.  Owner: E2 / E4

    Limit(i) = min( f(PD(i))            <- repayment probability, learned
                  , g(LoyaltyTier(i))   <- tier ceiling
                  , h(CLV(i))           <- never beyond recoverable value
                  , affordability(i) )  <- what one top-up can actually clear

Then every mandatory safety guard in conf/advance.yaml is applied, and each
one can only REDUCE the limit.

THE HEADLINE INSIGHT, and it falls straight out of Almadar's own numbers:

    smallest recharge card ......... 5 LYD
    نت في وقته data advance ........ 5 LYD, flat, for everyone

They are EQUAL, and the equality is the argument. A subscriber whose modal
top-up is the smallest card can clear a data advance in one recharge -- and
gets nothing for it. The whole card goes to the debt and they are returned to a
zero balance, immediately eligible to borrow again. The harm is a disincentive
to recharge rather than a locked door, and a deferred recharge on a prepaid
line is where silent churn starts.

(An earlier version of this file argued the debt EXCEEDED the smallest card and
could not be cleared at all. That was based on a 3 LYD card and it is retired.
conf/advance.yaml keeps `debt_exceeds_smallest_card: false` deliberately rather
than deleting the key, so a reader who remembers the stronger claim can see it
was withdrawn. The zero-residual argument is weaker and it is the true one.)

Both products gate on balance <= 0.5-1 LYD, so the eligible population is
selected on being broke -- the inverse of a risk filter. And because the two
products are mutually exclusive, distressed subscribers alternate between them,
a pattern nothing in the current design watches for.

The `affordability` term is the one the incumbent lacks entirely: never advance
more than the subscriber's own recharge behaviour shows they can clear AND
STILL HAVE SOMETHING LEFT. Use the MODAL recharge, not the mean -- the mean is
dragged up by one salary-week top-up they will not repeat.

The objective function is SUBSCRIBER SOLVENCY, not recovery yield. If you find
yourself optimising recovery after a default, you are working on the wrong
problem.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

import numpy as np

from cvm.api.schemas import AdvanceLimitRequest, AdvanceLimitResponse, AdvanceSafetyCheck
from cvm.config import load_conf

log = logging.getLogger(__name__)

AIRTIME, DATA = "airtime", "data"

# The API speaks the operator's product names and conf/advance.yaml is keyed by
# the generic ones. Mapped here, at the boundary, so neither side has to know
# about the other -- and so a new product fails loudly instead of silently
# falling through to the airtime branch.
PRODUCT_FROM_ENUM = {"rasid_fi_waqtuh": AIRTIME, "net_fi_waqtuh": DATA}


def _conf() -> dict:
    return load_conf("advance")


def _limits() -> dict:
    return _conf()["limit_function"]


def _guards() -> dict:
    return _conf()["safety_guards"]


def limit_from_pd(repayment_probability: float, product: str = AIRTIME) -> float:
    """f(PD): map calibrated repayment probability onto an LYD band.

    Airtime is constrained to the operator's real denominations (1, 3, 5) --
    we cannot invent a 2 LYD advance. Data is flat 5 LYD, so the only decision
    available there is grant or decline.

    CALIBRATED is doing real work in that first sentence. These bands are
    absolute probability thresholds, so a model that ranks perfectly and is
    systematically overconfident would push subscribers into higher bands and
    issue real credit against meaningless numbers.
    """
    if not 0.0 <= repayment_probability <= 1.0:
        raise ValueError(f"PD must be a probability, got {repayment_probability}")

    conf = _limits()
    if product == DATA:
        # Flat product: grant or decline, and the bar is higher because 5 LYD
        # consumes the whole of the smallest card.
        return (
            float(conf[DATA]["price_lyd"])
            if repayment_probability > conf[DATA]["grant_if_pd_above"]
            else 0.0
        )

    if product != AIRTIME:
        raise ValueError(f"unknown product {product!r}; expected {AIRTIME!r} or {DATA!r}")

    for band in sorted(conf[AIRTIME]["pd_to_limit_lyd"], key=lambda b: -b["min_pd"]):
        if repayment_probability >= band["min_pd"]:
            return float(band["limit_lyd"])
    return 0.0


def affordability_ceiling(modal_recharge_lyd: float) -> float:
    """Never issue a debt larger than one typical top-up can clear.

    The guard the incumbent has no equivalent of, and the one that catches the
    5-LYD-card / 5-LYD-debt trap.

    THE FRACTION IS STRICTLY BELOW 1.0 AND THAT IS THE POINT. At 1.0 a debt
    exactly equal to the modal recharge is permitted -- which is precisely the
    subscriber this guard exists to protect, because clearing it returns them
    to zero. At 0.6 the settlement leaves usable balance, so the top-up buys
    them service rather than nothing.
    """
    guard = _guards()["affordability_ceiling"]
    if not guard.get("enabled", True):
        raise ValueError(
            "affordability_ceiling is disabled in conf/advance.yaml. It is marked "
            "mandatory there and tests/guardrails/ asserts it."
        )
    fraction = guard["max_debt_as_fraction_of_modal_recharge"]
    if fraction >= 1.0:
        raise ValueError(
            f"max_debt_as_fraction_of_modal_recharge is {fraction}. At 1.0 a debt equal "
            "to the modal recharge is allowed, which is the zero-residual case this "
            "guard exists to prevent."
        )

    if modal_recharge_lyd is None or not np.isfinite(modal_recharge_lyd):
        # Unknown recharge behaviour is not evidence of capacity to repay.
        return 0.0

    ceiling = float(modal_recharge_lyd) * fraction
    if guard.get("never_exceed_smallest_denomination", False):
        ceiling = min(ceiling, float(guard["smallest_denomination_lyd"]))
    return max(0.0, ceiling)


def limit_from_tier(tier: str) -> float:
    """g(tier): the tier ceiling."""
    ceilings = _limits()["tier_ceiling_lyd"]
    key = str(tier).strip().lower()
    if key not in ceilings:
        # An unknown tier gets the most conservative ceiling, not the default
        # one. A typo in a tier name must not widen someone's credit.
        log.warning("unknown tier %r; falling back to the lowest ceiling", tier)
        return float(min(ceilings.values()))
    return float(ceilings[key])


def limit_from_clv(predicted_clv_lyd: float) -> float:
    """h(CLV): never advance beyond a fraction of recoverable lifetime value."""
    fraction = _limits()["max_fraction_of_clv"]
    if predicted_clv_lyd is None or not np.isfinite(predicted_clv_lyd):
        return 0.0
    return max(0.0, float(predicted_clv_lyd) * fraction)


def _step_down(limit_lyd: float) -> float:
    """5 -> 3 -> 1 -> 0. Never to an amount the operator does not offer."""
    rungs = sorted(_limits()[AIRTIME]["available_denominations_lyd"])
    lower = [d for d in rungs if d < limit_lyd]
    return float(max(lower)) if lower else 0.0


def apply_safety_guards(limit_lyd: float, features) -> tuple[float, list]:
    """Apply every mandatory guard. Returns (adjusted_limit, checks).

    Guards may only reduce the limit. A guard that increases it is a bug, and
    the final assertion here says so rather than trusting each branch.

    - affordability_ceiling: never exceed what one modal top-up clears
    - chronic_distress_exclusion: sustained shortfall -> excluded regardless
      of PD, including alternation between the two emergency products
    - cooling_off: minimum interval, monthly count and cumulative exposure caps
    - clv_bounded_exposure: re-checks the final number, not the input
    - lockout_risk: flag and step down a denomination when the risk is material
    """
    import pandas as pd

    guards = _guards()
    original = float(limit_lyd)
    limit = original
    checks: list[AdvanceSafetyCheck] = []

    def get(name: str, default=0.0):
        value = features.get(name, default) if hasattr(features, "get") else default
        return default if value is None or (isinstance(value, float) and np.isnan(value)) else value

    # --- affordability -------------------------------------------------------
    modal = get("modal_recharge_amount_lyd", float("nan"))
    ceiling = affordability_ceiling(modal)
    if limit > ceiling:
        checks.append(
            AdvanceSafetyCheck(
                guard="affordability_ceiling",
                passed=False,
                detail=(
                    f"a {limit:.0f} LYD debt against a {modal:.0f} LYD modal recharge leaves "
                    f"{modal - limit:.1f} LYD after settlement; the ceiling is {ceiling:.2f}"
                ),
            )
        )
        limit = min(limit, ceiling)
    else:
        checks.append(
            AdvanceSafetyCheck(
                guard="affordability_ceiling",
                passed=True,
                detail=f"{limit:.0f} LYD is within the {ceiling:.2f} LYD affordability ceiling",
            )
        )

    # --- chronic distress ----------------------------------------------------
    from cvm.features.distress import is_chronic_distress

    row = pd.DataFrame([dict(features)]) if not isinstance(features, pd.DataFrame) else features
    try:
        distressed = bool(is_chronic_distress(row).iloc[0])
    except KeyError:
        # No distress signals present at all. Refusing is the safe reading: a
        # guard that silently passes because its inputs are missing is a guard
        # that is not running.
        distressed = True
        log.warning("no distress signals available; treating as distressed")

    checks.append(
        AdvanceSafetyCheck(
            guard="chronic_distress_exclusion",
            passed=not distressed,
            detail=(
                "sustained shortfall on two or more signals -- excluded regardless of PD"
                if distressed
                else "no sustained-distress pattern"
            ),
        )
    )
    if distressed:
        limit = 0.0

    # --- cooling off ---------------------------------------------------------
    cooling = guards["cooling_off"]
    taken = float(get("advances_this_month", 0.0))
    exposure = float(get("cumulative_exposure_this_month_lyd", 0.0))
    days_since = float(get("days_since_last_advance", cooling["min_days_between_advances"]))

    breaches = []
    if days_since < cooling["min_days_between_advances"]:
        breaches.append(f"{days_since:.0f}d since the last advance")
    if taken >= cooling["max_advances_per_month"]:
        breaches.append(f"{taken:.0f} advances this month")
    if exposure + limit > cooling["max_cumulative_exposure_per_month_lyd"]:
        breaches.append(f"{exposure + limit:.0f} LYD cumulative exposure")

    checks.append(
        AdvanceSafetyCheck(
            guard="cooling_off",
            passed=not breaches,
            detail="; ".join(breaches) if breaches else "within interval, count and exposure caps",
        )
    )
    if breaches:
        limit = 0.0

    # --- CLV exposure, re-checked on the FINAL number ------------------------
    clv_cap = limit_from_clv(float(get("clv_12m", float("nan"))))
    checks.append(
        AdvanceSafetyCheck(
            guard="clv_bounded_exposure",
            passed=limit <= clv_cap,
            detail=f"{guards['clv_bounded_exposure']['max_fraction_of_clv']:.0%} of CLV is {clv_cap:.2f} LYD",
        )
    )
    limit = min(limit, clv_cap)

    # --- lockout risk --------------------------------------------------------
    lockout = guards["lockout_risk"]
    risk = float(get("lockout_risk", 0.0))
    flagged = risk > lockout["flag_if_probability_above"]
    if flagged and limit > 0:
        limit = _step_down(limit)
    checks.append(
        AdvanceSafetyCheck(
            guard="lockout_risk",
            passed=not flagged,
            detail=(
                f"{risk:.1%} chance of unpaid debt at day 14 -- stepped down to {limit:.0f} LYD"
                if flagged
                else f"{risk:.1%} chance of unpaid debt at day 14"
            ),
        )
    )

    # --- regulatory cap ------------------------------------------------------
    cap = float(_limits()["cap_regulatory_lyd"])
    checks.append(
        AdvanceSafetyCheck(
            guard="regulatory_cap",
            passed=limit <= cap,
            detail=f"the largest advance the operator offers is {cap:.0f} LYD",
        )
    )
    limit = min(limit, cap)

    _assert_only_reduced(original, limit)
    return max(0.0, limit), checks


def _assert_only_reduced(original: float, limit: float) -> None:
    """THE INVARIANT, in one place so it can be tested directly.

    Every guard above is written to reduce, but that is a property of five
    separate branches and a sixth could be written the wrong way round. This
    asserts it once, and a test exercises it once.
    """
    if limit > original + 1e-9:
        raise AssertionError(
            f"the guards raised the limit from {original:.2f} to {limit:.2f} LYD. A guard "
            "that increases a credit limit is a bug, not a feature."
        )


def decide_limit(
    payload: AdvanceLimitRequest, features: dict | None = None
) -> AdvanceLimitResponse:
    """Full path. Declining with a clear reason is a valid, often correct outcome."""
    import uuid

    features = {} if features is None else dict(features)
    raw_product = str(getattr(payload.product, "value", payload.product))
    product = PRODUCT_FROM_ENUM.get(raw_product, raw_product)
    if product not in (AIRTIME, DATA):
        raise ValueError(
            f"unknown product {raw_product!r}; expected one of {sorted(PRODUCT_FROM_ENUM)}"
        )

    pd_repay = float(features.get("repayment_probability", 0.0))
    lockout = float(features.get("lockout_risk", 0.0))
    modal = float(features.get("modal_recharge_amount_lyd", float("nan")))

    # The four terms. `min`, not a weighted blend: a high tier must not buy
    # back capacity that affordability has already refused.
    # Keyed by the GUARD names, not by shorthand. `binding_constraint` and
    # `reason_codes` both surface these strings, and a decline that reports
    # "affordability" where the guard is called "affordability_ceiling" cannot
    # be matched to a message or to a safety check by anything downstream.
    terms = {
        "pd_band": limit_from_pd(pd_repay, product),
        "tier_ceiling": limit_from_tier(features.get("loyalty_tier", "bronze")),
        "clv_bounded_exposure": limit_from_clv(float(features.get("clv_12m", float("nan")))),
        "affordability_ceiling": affordability_ceiling(modal),
    }
    binding = min(terms, key=lambda k: terms[k])
    limit = float(min(terms.values()))

    limit, checks = apply_safety_guards(limit, {**features, "lockout_risk": lockout})

    # Airtime must land on a real rung. Rounding DOWN, always -- rounding 2.4
    # up to 3 would hand back capacity a guard just removed.
    if product == AIRTIME and limit > 0:
        rungs = sorted(_limits()[AIRTIME]["available_denominations_lyd"])
        eligible = [d for d in rungs if d <= limit + 1e-9]
        limit = float(max(eligible)) if eligible else 0.0
    elif product == DATA:
        limit = (
            float(_limits()[DATA]["price_lyd"]) if limit >= _limits()[DATA]["price_lyd"] else 0.0
        )

    approved = limit > 0
    failed = [c.guard for c in checks if not c.passed]
    if not approved and not failed:
        failed = [binding]

    fee = _guards()["fee_structure"]
    reasons = failed if not approved else [f"binding_constraint:{binding}"]

    return AdvanceLimitResponse(
        subscriber_id=str(payload.subscriber_id),
        product=payload.product,
        approved=approved,
        limit_lyd=limit,
        repayment_probability=pd_repay,
        lockout_risk=lockout,
        lockout_flagged=lockout > _guards()["lockout_risk"]["flag_if_probability_above"],
        exceeds_modal_recharge=bool(np.isfinite(modal) and limit >= modal),
        modal_recharge_lyd=float(modal) if np.isfinite(modal) else 0.0,
        binding_constraint=binding,
        safety_checks=checks,
        cooling_off_until=_cooling_off_until(features),
        fallback_offer_id=(
            _limits()[DATA]["fallback_offer_id"] if (product == DATA and not approved) else None
        ),
        fee_lyd=float(fee["amount_lyd"]),
        reason_codes=reasons,
        customer_facing_reason_ar=_reason_ar(approved, failed, product),
        decision_log_id=str(uuid.uuid4()),
    )


def _cooling_off_until(features: dict) -> date | None:
    days = _guards()["cooling_off"]["min_days_between_advances"]
    since = features.get("days_since_last_advance")
    if since is None or not np.isfinite(since) or since >= days:
        return None
    return (datetime.now(UTC) + timedelta(days=days - float(since))).date()


def _reason_ar(approved: bool, failed: list[str], product: str) -> str:
    """One sentence in Arabic. A declined subscriber is told why, and offered
    the thing they can afford rather than nothing."""
    if approved:
        return "تمت الموافقة على السلفة."
    if "affordability_ceiling" in failed:
        return (
            "لا يمكن منح هذه السلفة لأن سدادها سيستهلك رصيد التعبئة بالكامل. "
            "يمكنك الاستفادة من باقة 50 ميجابايت بنصف دينار."
            if product == DATA
            else "لا يمكن منح هذه السلفة لأن سدادها سيستهلك رصيد التعبئة بالكامل."
        )
    if "chronic_distress_exclusion" in failed:
        return "السلفة غير متاحة حالياً. يرجى المحاولة بعد تحسّن نمط التعبئة."
    if "cooling_off" in failed:
        return "لقد استفدت من سلفة مؤخراً. يرجى الانتظار قبل طلب سلفة جديدة."
    return "السلفة غير متاحة حالياً."
