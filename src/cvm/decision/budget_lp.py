"""Budget-constrained cohort allocation.  Owner: E4

Knapsack / LP via PuLP: maximise expected retained margin subject to total
discount cost <= budget.

This is where "not spending is usually worth more than spending better" becomes
arithmetic. A blanket campaign across the full base at the same incentive costs
roughly 1,200,000 LYD per month for comparable or worse uplift, because most of
the spend lands on subscribers who would have recharged regardless. Targeted
selection saves roughly 1,050,000 LYD per month in wasted discount -- the larger
prize in the business case.
"""

from __future__ import annotations

import pandas as pd


def allocate(
    candidates: pd.DataFrame,
    budget_lyd: float,
    expected_margin_column: str = "expected_margin_lyd",
    cost_column: str = "discount_cost_lyd",
) -> pd.DataFrame:
    """Select the cohort. Returns candidates with a `selected` boolean column."""
    raise NotImplementedError("TODO(E4)")


def campaign_summary(allocation: pd.DataFrame) -> dict[str, float]:
    """Expected retained subscribers, total cost, net margin, ROI.

    These are the numbers the Campaign Builder screen renders and the business
    case quotes, so they must come from the solver rather than a spreadsheet.
    """
    raise NotImplementedError("TODO(E4)")
