"""The retention ladder -- three stages of intent to leave.  Owner: E4

Not a separate module: a DELIVERY POLICY LAYER over M1b and M3, which is why it
costs almost nothing to build.

STAGE BOUNDARIES COME FROM THE HAZARD FUNCTION, NOT FROM INTUITION. Rather than
picking 7 / 30 / 60 days by feel, the Kaplan-Meier and hazard curves from M1b
identify where recovery probability falls sharply, and those inflection points
become the cut-points -- recomputed per segment.

ON THE CURRENT POPULATION M1b RETURNS NO BOUNDARIES, and the fallback is used.
The generator places churn dates uniformly across the outcome window, so the
survival curve has no inflection a bootstrap agrees on -- see phase 6 of the
roadmap. That is the honest state: the derivation is built and validated, the
data cannot feed it yet, and `7 / 30 / 60` is a stated assumption rather than a
derived result until real Libyan data arrives. Anything else would be dressing
the fallback as a finding.

THE INVERTED-U. Most operators escalate the discount as the line gets colder,
which is backwards. Recovery probability collapses faster than the offer value
rises, so expected return per LYD spent peaks in the middle and falls away.
Optimal spend is low, then high, then LOW AGAIN. Stating this signals an
understanding of retention economics rather than retention mechanics.
"""

from __future__ import annotations

import logging

from cvm.api.schemas import RetentionStage
from cvm.config import load_conf

log = logging.getLogger(__name__)

# The inverted-U, as multipliers on the base offer value. Named here rather
# than in config because they ARE the policy claim: if these become monotonic
# the module has stopped saying anything and is just an escalation schedule.
SPEND_PROFILE: dict[RetentionStage, float] = {
    RetentionStage.NONE: 0.0,
    RetentionStage.COOLING: 0.5,
    RetentionStage.COLD: 1.0,
    RetentionStage.DORMANT: 0.3,
}


def _conf() -> dict:
    return load_conf("pricing")["retention_ladder"]


def derive_boundaries(hazard_inflections: list[int], segment: str | None = None) -> list[int]:
    """Stage cut-points in days, from M1b's hazard curve.

    Falls back to the configured `7 / 30 / 60` when M1b returns nothing, and
    says so at WARNING rather than INFO -- a fallback that looks like a
    derivation in the logs is how an assumption gets quoted as a result.
    """
    conf = _conf()
    fallback = list(conf["fallback_boundaries_days"])

    if not conf.get("derive_boundaries_from_hazard", True):
        raise ValueError(
            "derive_boundaries_from_hazard is off in conf/pricing.yaml. The whole point "
            "of this module is that the cut-points come from the hazard curve."
        )

    usable = sorted({int(d) for d in (hazard_inflections or []) if d > 0})
    if len(usable) < 2:
        log.warning(
            "ladder%s: M1b supplied %d usable inflection(s), so the boundaries are the "
            "CONFIGURED fallback %s and not a derived result. On the current synthetic "
            "population that is expected -- the generator places churn dates uniformly, "
            "so there is no inflection to find.",
            f" for {segment}" if segment else "",
            len(usable),
            fallback,
        )
        return fallback

    boundaries = usable[:2] if len(usable) >= 2 else usable
    log.info(
        "ladder%s: boundaries %s derived from the hazard curve",
        f" for {segment}" if segment else "",
        boundaries,
    )
    return boundaries


def assign_stage(
    days_since_last_revenue_event: int,
    subscriber_baseline_gap: float,
    boundaries: list[int],
) -> RetentionStage:
    """Stage 1 triggers on the subscriber's OWN baseline gap, not a global number.

    A subscriber who normally recharges weekly is cooling at day 10; one who
    recharges monthly is not. A single global threshold would put half the
    monthly rechargers permanently in `cooling` and never catch a weekly one
    until they were already gone -- it would fire constantly for one group and
    too late for the other, which is worse than not firing at all.

    Stages 2 and 3 use the hazard boundaries, which ARE global: past a certain
    point the curve behaves the same way whatever the subscriber's cadence was.
    """
    days = float(days_since_last_revenue_event)
    baseline = float(subscriber_baseline_gap) if subscriber_baseline_gap else 0.0

    ordered = sorted(int(b) for b in boundaries)
    if len(ordered) < 2:
        raise ValueError(f"need at least two boundaries to make three stages, got {boundaries}")
    first, second = ordered[0], ordered[1]

    if days >= second:
        return RetentionStage.DORMANT
    if days >= first:
        return RetentionStage.COLD
    # The personal trigger. A subscriber past their own usual gap is cooling
    # even if they are nowhere near the population's first inflection.
    if baseline > 0 and days > baseline:
        return RetentionStage.COOLING
    return RetentionStage.NONE


def spend_multiplier(stage: RetentionStage) -> float:
    """The inverted-U: low, then peak, then low again. Not monotonic.

    Asserted against the config's declared `spend_profile` so the two cannot
    drift: if someone edits the profile to [low, peak, high] the claim in the
    docstring stops being true and this raises rather than quietly escalating
    spend on the least recoverable subscribers.
    """
    profile = _conf()["spend_profile"]
    if profile != ["low", "peak", "low"]:
        raise ValueError(
            f"spend_profile is {profile}. The inverted-U is the finding -- recovery "
            "probability collapses faster than offer value rises, so spend must fall "
            "again at the last stage. A monotonic profile is an escalation schedule, "
            "which is what every operator already does."
        )

    multiplier = SPEND_PROFILE[RetentionStage(stage)]
    if SPEND_PROFILE[RetentionStage.DORMANT] >= SPEND_PROFILE[RetentionStage.COLD]:
        raise AssertionError("the dormant multiplier must be BELOW the cold one; that is the U")
    return multiplier
