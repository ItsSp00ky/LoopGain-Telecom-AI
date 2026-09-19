"""Budget-constrained cohort allocation.  Owner: E4

Knapsack / LP via PuLP: maximise expected retained margin NET OF THE DISCOUNT,
subject to total discount cost <= budget.

This is where "not spending is usually worth more than spending better" becomes
arithmetic. A blanket campaign across the full base at the same incentive costs
roughly 1,200,000 LYD per month for comparable or worse uplift, because most of
the spend lands on subscribers who would have recharged regardless. Targeted
selection saves roughly 1,050,000 LYD per month in wasted discount -- the larger
prize in the business case.

Those two are the PROPOSAL'S figures, for the whole base. campaign_summary
computes the real ones for whatever cohort it is handed, and does it twice: at
equal spend, which measures the targeting, and against treating everybody,
which measures the discount avoided. Reporting only the second is how the
screen came to claim a saving of 0 LYD.

WHY AN LP AND NOT A SORT. With one constraint and divisible costs, sorting by
net-margin-per-LYD is optimal and the solver is overkill -- and it is the right
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

    THE MARGIN COLUMN IS GROSS, before the discount is paid for. This is the
    contract and it was not written down, so the Campaign Builder supplied
    M3's `expected_value_lyd` -- which is already `uplift x CLV - cost` -- and
    campaign_summary subtracted the cost a second time. The screen understated
    net margin by exactly the campaign cost, 1,220 LYD on the default cohort.

    Candidates whose margin does not clear their cost are excluded before the
    solver sees them. NET, not gross: treating someone whose uplift buys 3 LYD
    of retained value with a 5 LYD offer destroys 2 LYD, and `margin > 0` waves
    that through. `margin > cost` is the same break-even the rest of the system
    is built on -- uplift x CLV > cost, 1.0417 pp at the headline figures.

    They are excluded rather than left for the LP to reject because leaving
    them in makes the rejection count meaningless: "the guardrail rejected
    40,000 candidates" should mean the budget bound, not that 40,000 rows were
    never viable. The two are reported separately.
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
    viable = (frame[expected_margin_column] > frame[cost_column]) & (frame[cost_column] >= 0)
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

    # NET of the discount. Maximising gross margin ranks a candidate who
    # returns 6 LYD for 5 above one who returns 5 for 1, which is backwards.
    # Identical to maximising gross only when every cost is the same, which is
    # true of today's blended incentive and will not survive the first
    # per-segment offer.
    problem += pulp.lpSum((pool.loc[i, margin] - pool.loc[i, cost]) * pick[i] for i in pool.index)
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

    net = pool[margin] - pool[cost]
    solver_margin = float(net.loc[chosen].sum())
    greedy_margin = float(net.loc[greedy].sum())
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
    """NET margin per LYD, descending, until the budget runs out.

    Optimal for a single divisible constraint, which is what there is today.
    A free candidate (zero cost) is taken whenever its margin is positive.
    """
    ratio = (pool[margin] - pool[cost]) / pool[cost].replace(0.0, 1e-9)
    ordered = pool.assign(_ratio=ratio).sort_values("_ratio", ascending=False)

    spent, chosen = 0.0, []
    for index, row in ordered.iterrows():
        if spent + row[cost] <= budget + 1e-9:
            chosen.append(index)
            spent += float(row[cost])
    return pd.Index(chosen)


def campaign_summary(
    allocation: pd.DataFrame,
    cohort: pd.DataFrame | None = None,
    expected_margin_column: str = "expected_margin_lyd",
    cost_column: str = "discount_cost_lyd",
) -> dict[str, float]:
    """Expected retained subscribers, total cost, net margin, ROI.

    These are the numbers the Campaign Builder screen renders and the business
    case quotes, so they must come from the solver rather than a spreadsheet.

    `cohort` IS THE BLANKET BASELINE, and passing it is the whole point.

    A blanket campaign is one that ignores the guardrails and treats everybody.
    This function used to compute that baseline from `allocation`, which is
    whatever survived the caller's own filtering -- and the Campaign Builder
    filters out sleeping dogs, negative expected value and sub-ceiling CLV
    before it calls. So "blanket" meant "every candidate the guardrails already
    approved", the two populations were identical whenever the budget did not
    bind, and the screen reported a saving of **0 LYD** while a chart beside it
    showed 227 of 497 removed. The 227 were the saving. They were not counted.

    Pass the matched cohort MINUS the control holdout. Keep the guardrail
    rejections in: measuring what they save is the entire purpose. Leave the
    holdout out: it is untreated in both arms, so it belongs to neither.

    Omitting `cohort` still falls back to `allocation`, which is correct when
    the caller did no filtering of its own -- and `blanket_baseline` in the
    result says which population was used, so the answer can never again look
    the same whether or not anyone thought about it.
    """
    frame = pd.DataFrame(allocation)
    for column in (expected_margin_column, cost_column, SELECTED):
        if column not in frame.columns:
            raise KeyError(f"{column!r} is absent; run allocate() first")

    picked = frame[frame[SELECTED]]
    cost = float(picked[cost_column].sum())
    margin = float(picked[expected_margin_column].sum())

    if cohort is None:
        baseline, baseline_name = frame, "allocation"
        log.warning(
            "campaign_summary got no cohort, so the blanket baseline is the allocation "
            "frame itself. Correct only if nothing was filtered before allocate()."
        )
    else:
        baseline = pd.DataFrame(cohort)
        baseline_name = "cohort"
        for column in (expected_margin_column, cost_column):
            if column not in baseline.columns:
                raise KeyError(f"{column!r} is absent from the cohort passed as the baseline")

    # Negatives included, deliberately. Treating a sleeping dog has a negative
    # expected margin, and that destruction IS what a blanket campaign buys --
    # clipping it away would make the thing this comparison exists to expose
    # invisible.
    blanket_cost = float(baseline[cost_column].sum())
    blanket_margin = float(baseline[expected_margin_column].sum())
    blanket_net = blanket_margin - blanket_cost

    net = margin - cost

    # THE SAME-BUDGET COMPARISON, which is the fair one and the reason there
    # are two.
    #
    # An unconstrained blanket campaign is allowed to outspend the budget, so
    # `net - blanket_net` mixes two questions -- is targeting better, and was
    # the budget big enough -- and answers them with one number that goes
    # NEGATIVE when the budget binds. On the phase-8 fixture it read -2,075
    # LYD, which reads as "targeting lost money" and means "targeting was given
    # 1,000 LYD and blanket was given 2,400".
    #
    # Holding spend constant isolates the part that is about targeting. With a
    # uniform incentive a random selection of k subscribers returns k x the
    # cohort mean in expectation, exactly -- no sampling, no seed, no ordering
    # to argue about. That is the untargeted campaign the same money buys.
    mean_cost = float(baseline[cost_column].mean()) if len(baseline) else 0.0
    affordable = min(int(cost // mean_cost), len(baseline)) if mean_cost > 0 else len(baseline)
    mean_net = (blanket_net / len(baseline)) if len(baseline) else 0.0
    same_budget_net = affordable * mean_net

    # Where the saving came from. The guardrails and the budget both decline
    # people, for completely different reasons, and a single number hides which
    # one is doing the work -- which is how a 0 went unnoticed.
    viable = frame.get("viable", pd.Series(True, index=frame.index)).fillna(False)
    unselected_viable = float(frame.loc[viable & ~frame[SELECTED], cost_column].sum())
    saving = blanket_cost - cost

    summary = {
        "candidates": len(frame),
        "selected": int(frame[SELECTED].sum()),
        "not_viable": int((~viable).sum()),
        "cost_lyd": cost,
        "expected_margin_lyd": margin,
        "net_margin_lyd": net,
        "roi": (margin / cost) if cost > 0 else float("inf"),
        "expected_retained": float(picked.get("uplift", pd.Series(0.0, index=picked.index)).sum()),
        "blanket_baseline": baseline_name,
        "blanket_candidates": len(baseline),
        "blanket_cost_lyd": blanket_cost,
        "blanket_net_margin_lyd": blanket_net,
        # Discount not spent.
        "saving_versus_blanket_lyd": saving,
        # Against an unconstrained blanket campaign. Counts the value not
        # destroyed as well as the discount saved -- but goes negative when the
        # budget binds, because the two arms are not spending the same money.
        "net_margin_versus_blanket_lyd": net - blanket_net,
        # Against the same money spent without targeting. This is the one that
        # answers "is the targeting worth anything", and the one a screen
        # should lead with.
        "blanket_same_budget_treated": affordable,
        "blanket_same_budget_net_margin_lyd": same_budget_net,
        "net_margin_versus_same_budget_lyd": net - same_budget_net,
        # Of the discount saved, how much each mechanism accounts for.
        "saving_from_guardrails_lyd": max(saving - unselected_viable, 0.0),
        "saving_from_budget_lyd": min(unselected_viable, saving),
    }
    log.info(
        "campaign: %d of %d treated for %.0f LYD, net margin %.0f, ROI %.2fx; "
        "the same %.0f LYD spent untargeted would net %.0f, so targeting is worth "
        "%.0f; an unconstrained blanket over %d (%s) would cost %.0f for a net of "
        "%.0f, so targeting also avoids %.0f of discount",
        summary["selected"],
        summary["candidates"],
        cost,
        net,
        summary["roi"],
        cost,
        same_budget_net,
        summary["net_margin_versus_same_budget_lyd"],
        summary["blanket_candidates"],
        baseline_name,
        blanket_cost,
        blanket_net,
        saving,
    )
    return summary
