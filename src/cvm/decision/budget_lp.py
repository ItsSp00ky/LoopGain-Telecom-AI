"""Budget-constrained cohort allocation.  Owner: E4

Knapsack / LP via PuLP: maximise expected retained margin subject to total
discount cost <= budget.

This is where "not spending is usually worth more than spending better" becomes
arithmetic. A blanket campaign across the full base at the same incentive costs
roughly 1,200,000 LYD per month for comparable or worse uplift, because most of
the spend lands on subscribers who would have recharged regardless. Targeted
selection saves roughly 1,050,000 LYD per month in wasted discount -- the larger
prize in the business case.

WHY AN LP AND NOT A SORT. With one constraint and divisible costs, sorting by
margin-per-LYD is optimal and the solver is overkill -- and it is the right
answer today. The solver earns its place the moment a second constraint
appears, which it will: per-segment quotas so one cohort cannot absorb the
whole budget, a channel capacity limit, a minimum treated count for the
holdout to stay measurable. Each of those breaks the greedy ordering and none
of them changes this function's signature.

The greedy solution is computed anyway and compared. If they disagree by more
than rounding, something in the constraint set is doing more than it looks --
and that is worth a log line rather than silent acceptance.
"""

from __future__ import annotations

import logging

import pandas as pd

from cvm.config import load_conf

log = logging.getLogger(__name__)

SELECTED = "selected"


def _conf() -> dict:
    return load_conf("pricing")["guardrails"]["budget"]


def allocate(
    candidates: pd.DataFrame,
    budget_lyd: float | None = None,
    expected_margin_column: str = "expected_margin_lyd",
    cost_column: str = "discount_cost_lyd",
) -> pd.DataFrame:
    """Select the cohort. Returns candidates with a `selected` boolean column.

    Candidates with a NON-POSITIVE expected margin are excluded before the
    solver sees them. Not because the LP would pick them -- it would not -- but
    because leaving them in makes the rejection count meaningless: "the
    guardrail rejected 40,000 candidates" should mean the budget bound, not
    that 40,000 rows were never viable in the first place. The two are reported
    separately.
    """
    conf = _conf()
    if not conf.get("enabled", True):
        raise ValueError("the budget guardrail is disabled in conf/pricing.yaml")
    budget = float(conf["default_campaign_budget_lyd"] if budget_lyd is None else budget_lyd)
    if budget < 0:
        raise ValueError(f"the budget must be non-negative, got {budget}")

    frame = pd.DataFrame(candidates).copy()
    for column in (expected_margin_column, cost_column):
        if column not in frame.columns:
            raise KeyError(
                f"{column!r} is absent; allocate needs a margin and a cost per candidate"
            )

    frame[SELECTED] = False
    viable = (frame[expected_margin_column] > 0) & (frame[cost_column] >= 0)
    frame["viable"] = viable

    pool = frame[viable]
    if pool.empty:
        log.warning("no candidate has a positive expected margin; nothing allocated")
        return frame

    selected_index = _solve(pool, budget, expected_margin_column, cost_column)
    frame.loc[selected_index, SELECTED] = True

    cost = float(frame.loc[frame[SELECTED], cost_column].sum())
    if cost > budget + 1e-6:
        raise AssertionError(f"allocated {cost:.2f} LYD against a {budget:.2f} budget")

    log.info(
        "allocation: %d of %d selected (%d were never viable), %.2f of %.2f LYD spent",
        int(frame[SELECTED].sum()),
        len(frame),
        int((~viable).sum()),
        cost,
        budget,
    )
    return frame


def _solve(pool: pd.DataFrame, budget: float, margin: str, cost: str) -> pd.Index:
    """PuLP where it is available, greedy where it is not -- and compared."""
    greedy = _greedy(pool, budget, margin, cost)

    try:
        import pulp
    except ImportError:
        log.warning("PuLP is not installed; using the greedy ordering")
        return greedy

    problem = pulp.LpProblem("cohort_allocation", pulp.LpMaximize)

    # `problem.add_variable` rather than `LpVariable(...)`: the constructor is
    # deprecated in PuLP 4.0 and emits one DeprecationWarning PER VARIABLE.
    # At one variable per candidate that is thousands of lines of noise, which
    # is how a real warning gets missed. Falls back where the method is absent.
    if hasattr(problem, "add_variable"):
        pick = {i: problem.add_variable(f"x_{i}", cat="Binary") for i in pool.index}
    else:  # pragma: no cover -- PuLP < 3.3
        pick = {i: pulp.LpVariable(f"x_{i}", cat="Binary") for i in pool.index}

    problem += pulp.lpSum(pool.loc[i, margin] * pick[i] for i in pool.index)
    problem += pulp.lpSum(pool.loc[i, cost] * pick[i] for i in pool.index) <= budget

    solver_name = _conf().get("solver", "PULP_CBC_CMD")
    try:
        solver = getattr(pulp, solver_name)(msg=False)
        problem.solve(solver)
    except Exception as exc:  # a missing CBC binary must not lose the campaign
        log.warning("%s unavailable (%s); using the greedy ordering", solver_name, exc)
        return greedy

    if pulp.LpStatus[problem.status] != "Optimal":
        log.warning("solver returned %s; using the greedy ordering", pulp.LpStatus[problem.status])
        return greedy

    chosen = pd.Index([i for i in pool.index if pick[i].value() and pick[i].value() > 0.5])

    solver_margin = float(pool.loc[chosen, margin].sum())
    greedy_margin = float(pool.loc[greedy, margin].sum())
    if solver_margin < greedy_margin - 1e-6:
        log.warning(
            "the solver found %.2f LYD of margin and greedy found %.2f -- using greedy",
            solver_margin,
            greedy_margin,
        )
        return greedy
    if solver_margin > greedy_margin + 1e-6:
        log.info(
            "the solver beat greedy by %.2f LYD, so a constraint is doing more than "
            "ordering by margin-per-LYD",
            solver_margin - greedy_margin,
        )
    return chosen


def _greedy(pool: pd.DataFrame, budget: float, margin: str, cost: str) -> pd.Index:
    """Margin per LYD, descending, until the budget runs out.

    Optimal for a single divisible constraint, which is what there is today.
    A free candidate (zero cost) is taken whenever its margin is positive.
    """
    ratio = pool[margin] / pool[cost].replace(0.0, 1e-9)
    ordered = pool.assign(_ratio=ratio).sort_values("_ratio", ascending=False)

    spent, chosen = 0.0, []
    for index, row in ordered.iterrows():
        if spent + row[cost] <= budget + 1e-9:
            chosen.append(index)
            spent += float(row[cost])
    return pd.Index(chosen)


def campaign_summary(allocation: pd.DataFrame) -> dict[str, float]:
    """Expected retained subscribers, total cost, net margin, ROI.

    These are the numbers the Campaign Builder screen renders and the business
    case quotes, so they must come from the solver rather than a spreadsheet.

    The BLANKET COMPARISON is computed here too, because "targeting saves
    1,050,000 LYD" is the larger half of the business case and it should be an
    output of the allocation rather than a figure in a slide. Blanket cost is
    every candidate treated at the same incentive; the saving is the difference.
    """
    frame = pd.DataFrame(allocation)
    for column in ("expected_margin_lyd", "discount_cost_lyd", SELECTED):
        if column not in frame.columns:
            raise KeyError(f"{column!r} is absent; run allocate() first")

    picked = frame[frame[SELECTED]]
    cost = float(picked["discount_cost_lyd"].sum())
    margin = float(picked["expected_margin_lyd"].sum())

    blanket_cost = float(frame["discount_cost_lyd"].sum())
    blanket_margin = float(frame["expected_margin_lyd"].clip(lower=None).sum())

    summary = {
        "candidates": len(frame),
        "selected": int(frame[SELECTED].sum()),
        "not_viable": int((~frame.get("viable", pd.Series(True, index=frame.index))).sum()),
        "cost_lyd": cost,
        "expected_margin_lyd": margin,
        "net_margin_lyd": margin - cost,
        "roi": (margin / cost) if cost > 0 else float("inf"),
        "expected_retained": float(picked.get("uplift", pd.Series(0.0, index=picked.index)).sum()),
        "blanket_cost_lyd": blanket_cost,
        "blanket_net_margin_lyd": blanket_margin - blanket_cost,
        "saving_versus_blanket_lyd": blanket_cost - cost,
    }
    log.info(
        "campaign: %d of %d treated for %.0f LYD, net margin %.0f, ROI %.2fx; "
        "a blanket campaign would cost %.0f, so targeting saves %.0f",
        summary["selected"],
        summary["candidates"],
        cost,
        summary["net_margin_lyd"],
        summary["roi"],
        blanket_cost,
        summary["saving_versus_blanket_lyd"],
    )
    return summary
