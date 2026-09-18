"""Off-peak offloading and per-cell trough detection.  Owner: E4

Peak-hour capacity is what drives network capex, so shifting load has real
avoided-capex value beyond the near-zero marginal cost of an off-peak bit.

ALMADAR'S OFF-PEAK WINDOW IS THE MORNING, NOT THE NIGHT. The operator sells
عروض الصبح: 1 LYD, unlimited data AND unlimited voice, valid 06:00-11:00 only.
That product is the anchor for this module, and its existence is unusually
strong evidence -- the operator has already priced its own spare capacity and
told us when that capacity is. M3 personalises an existing product rather
than proposing a new one.

Two refinements over simply reselling that pass, and both matter:

PER-CELL TROUGH DETECTION. The operator's 06:00-11:00 band is national. Each
cell's own 24-hour load curve is analysed to find its actual minimum-utilisation
window, and validity hours are set PER SITE. A congested Tripoli sector and a
lightly loaded Ghat sector do not trough at the same time. The national band is
the fallback, which makes this a refinement of a real product rather than a
guess. If a detected trough lands far outside 05:00-13:00, suspect the load
curve rather than celebrating a discovery.

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


def detect_trough(load_curve_24h: np.ndarray, min_hours: int = 3, max_hours: int = 6) -> tuple[int, int]:
    """Return (start_hour, end_hour) of this cell's minimum-utilisation band."""
    raise NotImplementedError("TODO(E4)")


def detect_troughs_batch(load_curves: dict[str, np.ndarray]) -> dict[str, tuple[int, int]]:
    """Trough detection across every cell at once. Cached -- a cell's load
    curve changes slowly, and recomputing it per offer would blow the latency
    budget."""
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