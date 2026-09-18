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

    Compares expected revenue with and without the grant. The downgrade term is
    the gap between the bundle held and the next rung down, floored at the base
    monthly -- NOT the full bundle price, because nobody drops below the base.
    Must report the implied erosion so it can be checked against
    ``max_simulated_arpu_erosion`` in conf/pricing.yaml.
    """
    raise NotImplementedError("TODO(E4)")
