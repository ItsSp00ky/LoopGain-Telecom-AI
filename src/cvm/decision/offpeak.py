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

CANNIBALISATION GUARD. A 1 LYD unlimited morning pass is cheap enough to pull
heavy users down off a 35-80 LYD monthly bundle -- and at 06:00-11:00 it covers
the commute and the working morning, which is real usage for a lot of people.
So eligibility excludes subscribers whose peak-hour usage would simply shift
rather than grow, the pass is granted as ADDITIVE rather than substitutable,
and a simulated margin check runs before any cohort is approved. This is the
single most important commercial critique of the idea, and it is answered in
code rather than in a footnote.
"""

from __future__ import annotations

import numpy as np


def offpeak_window() -> tuple[int, int]:
    """The operator's published off-peak hours, from conf/pricing.yaml.

    Returns (6, 11). There is deliberately no trough-detection function in
    this module: the window is a known fact, not something to infer.
    """
    raise NotImplementedError("TODO(E4)")


def would_shift_not_grow(peak_usage: float, offpeak_usage: float, headroom: float) -> bool:
    """True when a morning pass would displace paid usage rather than add to it."""
    raise NotImplementedError("TODO(E4)")


def simulate_cohort_margin(cohort, offer_id: str) -> dict[str, float]:
    """Simulated margin check. Must run before any cohort is approved.

    Compares expected revenue with and without the grant, including the ARPU
    lost when a subscriber downgrades off a monthly bundle they no longer need.
    """
    raise NotImplementedError("TODO(E4)")