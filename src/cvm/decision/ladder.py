"""The retention ladder -- three stages of intent to leave.  Owner: E4

Not a separate module: a DELIVERY POLICY LAYER over M1b and M3, which is why it
costs almost nothing to build.

STAGE BOUNDARIES COME FROM THE HAZARD FUNCTION, NOT FROM INTUITION. Rather than
picking 7 / 30 / 60 days by feel, the Kaplan-Meier and hazard curves from M1b
identify where recovery probability falls sharply, and those inflection points
become the cut-points -- recomputed per segment.

THE INVERTED-U. Most operators escalate the discount as the line gets colder,
which is backwards. Recovery probability collapses faster than the offer value
rises, so expected return per LYD spent peaks in the middle and falls away.
Optimal spend is low, then high, then LOW AGAIN. Stating this signals an
understanding of retention economics rather than retention mechanics.
"""

from __future__ import annotations

from cvm.api.schemas import RetentionStage


def derive_boundaries(hazard_inflections: list[int], segment: str | None = None) -> list[int]:
    """Stage cut-points in days, from M1b's hazard curve."""
    raise NotImplementedError("TODO(E4)")


def assign_stage(
    days_since_last_revenue_event: int,
    subscriber_baseline_gap: float,
    boundaries: list[int],
) -> RetentionStage:
    """Stage 1 triggers on the subscriber's OWN baseline gap, not a global number.

    A subscriber who normally recharges weekly is cooling at day 10; one who
    recharges monthly is not.
    """
    raise NotImplementedError("TODO(E4)")


def spend_multiplier(stage: RetentionStage) -> float:
    """The inverted-U: low, then peak, then low again. Not monotonic."""
    raise NotImplementedError("TODO(E4)")