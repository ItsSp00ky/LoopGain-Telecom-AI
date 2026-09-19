"""Off-peak offloading.  Owner: E4

Peak-hour capacity is what drives network capex, so shifting load has real
avoided-capex value beyond the near-zero marginal cost of an off-peak bit.

ALMADAR'S OFF-PEAK WINDOW IS THE MORNING, NOT THE NIGHT. The operator sells
عروض الصبح: 1 LYD, unlimited data AND unlimited voice, valid 06:00-11:00 only.
That product is the anchor for this module, and its existence is unusually
strong evidence -- the operator has already priced its own spare capacity and
told us when that capacity is. M3 personalises an existing product rather
than proposing a new one.

Two refinements over simply reselling that pass, and both matter:

ONE NATIONAL WINDOW. Per-cell trough detection was dropped along with
geography: it needed cell load curves this branch no longer models, and it was
only ever a refinement of the window the operator already publishes. Using the
real published hours is not a compromise -- it is the answer, and it is better
evidence than a trough we detected ourselves.

CANNIBALISATION IS A LADDER PROBLEM, NOT A PRODUCT PROBLEM. The obvious
objection -- "a 1 LYD pass will pull people off their monthly bundle" -- is
half right, and the half it gets wrong matters. نت 20 at 35 LYD is the BASE
monthly: what a subscriber needs to have data outside 06:00-11:00 at all. Free
mornings do not remove that need, so the base is not substitutable and the
subscribers sitting on it have nowhere to fall.

The exposed population is only those ABOVE the base -- نت 40 at 50, نت 80 at
80, the 5G monthlies, Elite, Family -- for whom the pass can justify stepping
DOWN a rung. The loss is then the gap between rungs, not the whole bundle:
14 LYD/month for one rung, 44 for two.

So eligibility keys on the bundle actually held, excludes subscribers whose
peak-hour usage would simply shift rather than grow, grants the pass as
ADDITIVE rather than substitutable, and runs a simulated margin check before
any cohort is approved. The guard is mechanistic rather than statistical,
which is why it is answerable in code rather than in a footnote.
"""

from __future__ import annotations

import logging

import pandas as pd

from cvm.config import load_conf

log = logging.getLogger(__name__)


def _conf() -> dict:
    return load_conf("pricing")["offpeak"]


def _cannibalisation() -> dict:
    return load_conf("pricing")["guardrails"]["cannibalisation"]


def offpeak_window() -> tuple[int, int]:
    """The operator's published off-peak hours, from conf/pricing.yaml.

    Returns (6, 11). There is deliberately no trough-detection function in
    this module: the window is a known fact, not something to infer.
    """
    conf = _conf()
    if conf.get("per_cell_trough_detection", False):
        raise ValueError(
            "per_cell_trough_detection is on, and this branch models no cell load "
            "curves. The operator publishes its own window; detecting a different one "
            "would be inventing evidence."
        )
    window = conf["window"]
    return int(window["start_hour"]), int(window["end_hour"])


def would_shift_not_grow(peak_usage: float, offpeak_usage: float, headroom: float) -> bool:
    """True when a morning pass would displace paid usage rather than add to it.

    THE DISTINCTION THE WHOLE MODULE TURNS ON. A subscriber who already uses
    their data in the morning gains nothing from free mornings -- they simply
    stop paying for what they were already doing, and the grant is pure
    revenue loss. A subscriber whose usage is concentrated at peak, with
    headroom to use more, genuinely adds off-peak consumption.

    `headroom` is how much unmet demand they have: near zero means their
    current bundle already covers them, so a free window cannot grow anything.
    """
    total = float(peak_usage) + float(offpeak_usage)
    if total <= 0:
        # No observed usage at all. There is nothing to grow, so granting is
        # not justified on offload grounds.
        return True

    already_offpeak = float(offpeak_usage) / total
    minimum = _conf()["min_offpeak_data_ratio_to_qualify"]

    # Two ways to be a shifter: already doing it in the morning, or having no
    # unmet demand to move.
    return already_offpeak >= (1.0 - minimum) or float(headroom) <= 0.0


def simulate_cohort_margin(cohort, offer_id: str | None = None) -> dict[str, float]:
    """Simulated margin check. Must run before any cohort is approved.

    Compares expected revenue with and without the grant. The downgrade term is
    the gap between the bundle held and the next rung down, floored at the base
    monthly -- NOT the full bundle price, because nobody drops below the base.
    Must report the implied erosion so it can be checked against
    ``max_simulated_arpu_erosion`` in conf/pricing.yaml.
    """
    conf = _cannibalisation()
    base_price = float(conf["base_monthly_price_lyd"])
    cap = float(conf["max_simulated_arpu_erosion"])
    offer_id = offer_id or _conf()["anchor_product"]

    frame = pd.DataFrame(cohort).copy()
    if "current_monthly_bundle_lyd" not in frame.columns:
        raise KeyError(
            "current_monthly_bundle_lyd is required. Exposure depends on the bundle "
            "actually HELD -- a subscriber on the base monthly has nowhere to fall."
        )

    held = frame["current_monthly_bundle_lyd"].astype("float64").fillna(base_price)

    # EXEMPT AT OR BELOW THE BASE. This is the structural argument, applied
    # per subscriber rather than assumed for the cohort.
    exposed = held > base_price if conf.get("exempt_at_or_below_base_monthly", True) else held > 0

    # The loss is the gap to the NEXT RUNG DOWN, floored at the base -- not the
    # whole bundle. A نت 40 holder at 50 LYD who steps down to نت 20 at 35 loses
    # 15, not 50, and presenting it as 50 would make the guard unfalsifiable.
    rungs = _ladder_rungs()
    next_down = held.map(lambda p: _next_rung_down(p, rungs, base_price))
    downgrade_loss = (held - next_down).where(exposed, 0.0)

    # Only subscribers who would SHIFT rather than grow are assumed to
    # downgrade. The others are additive by construction.
    shifts = (
        frame["would_shift_not_grow"].astype(bool)
        if "would_shift_not_grow" in frame.columns
        else pd.Series(False, index=frame.index)
    )
    expected_loss = float((downgrade_loss * shifts).sum())

    baseline_revenue = float(held.sum())
    erosion = expected_loss / baseline_revenue if baseline_revenue else 0.0
    passed = erosion <= cap

    result = {
        "offer_id": offer_id,
        "cohort_size": len(frame),
        "exposed": int(exposed.sum()),
        "exempt_at_or_below_base": int((~exposed).sum()),
        "assumed_downgraders": int((exposed & shifts).sum()),
        "baseline_revenue_lyd": baseline_revenue,
        "expected_loss_lyd": expected_loss,
        "simulated_arpu_erosion": erosion,
        "max_allowed_erosion": cap,
        "passed": passed,
    }
    log.log(
        logging.INFO if passed else logging.WARNING,
        "offpeak simulation for %s: %d exposed of %d (%d exempt at or below the %.0f LYD "
        "base), erosion %.4f against a %.4f cap -- %s",
        offer_id,
        result["exposed"],
        len(frame),
        result["exempt_at_or_below_base"],
        base_price,
        erosion,
        cap,
        "PASS" if passed else "BLOCKED",
    )
    return result


def _ladder_rungs() -> list[float]:
    """Monthly data bundle prices, ascending, from the real catalogue."""
    catalogue = load_conf("catalogue")
    prices = {
        float(item["price_lyd"])
        for family in catalogue["families"].values()
        for item in family.get("items", [])
        if item.get("validity_days", 0) >= 28
    }
    return sorted(prices)


def _next_rung_down(price: float, rungs: list[float], floor: float) -> float:
    """The rung immediately below `price`, never below the base monthly."""
    lower = [r for r in rungs if floor <= r < price]
    return float(max(lower)) if lower else float(min(floor, price))
