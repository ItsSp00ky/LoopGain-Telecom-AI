"""Emergency credit advice (ticket T19, decision 23).

The operator sells two emergency credit products, both confirmed from its own
documents and recorded in `data/operator/market.toml` by T16:

- `رصيد في وقته`, an airtime advance of 1, 3 or 5 LYD, offered when the balance is at or
  below 0.5 LYD and recovered at the first recharge.
- `نت في وقته`, a flat 5 LYD data advance for 2 GB over 72 hours, offered when the balance
  is at or below 1 LYD.

This module **advises a limit**. It grants nothing, and it is a proposal for a person in
exactly the way a retention offer is (decision 14).

The rule it applies is the one `Ali_Branch` added and the operator's own design lacks:
never advise a debt larger than the subscriber's own recharge behaviour shows they can
clear in one top-up **and still have something left**.

Both products gate on the subscriber being nearly out of money, so the eligible population
is selected on being broke.
That is the inverse of a risk filter, which is why the ceiling is the whole of the logic
here rather than one guard among many.

There is no repayment model, and there will not be one without repayment data (decision
15).
Nothing in this module estimates a probability of repayment.
"""

import numpy as np
import pandas as pd

from prepaid_churn.data import PROJECT_ROOT
from prepaid_churn.operator_market import InvalidCatalogueError, lyd_rate, validate_market
from prepaid_churn.schema import ID
from prepaid_churn.windows import Window, window_features

REPORTS_DIR = PROJECT_ROOT / "reports"

AIRTIME = "airtime"
DATA = "data"
DECLINED = 0.0

# Ported from `Ali_Branch`'s `conf/advance.yaml`, with his reason kept intact.
# The fraction is strictly below 1.0 and that is the entire point.
# At 1.0 a debt exactly equal to the typical top-up is allowed, which is precisely the
# subscriber the guard exists to protect: clearing it returns them to a zero balance.
# At 0.6 the settlement leaves usable balance, so the top-up buys them service.
MAX_DEBT_FRACTION = 0.6

ADVICE_COLUMNS = (
    ID,
    "topup_prev_lyd",
    "topup_cur_lyd",
    "typical_topup_lyd",
    "affordability_ceiling_lyd",
    "airtime_limit_lyd",
    "airtime_residual_lyd",
    "data_advance_advised",
    "advice_code",
    "advice_reason_en",
    "advice_reason_ar",
)

REASONS = {
    "no_recharge": (
        "No advice: no recharge in the window, so there is no evidence of capacity to repay.",
        "لا نصيحة: لا توجد تعبئة خلال الفترة، فلا يوجد دليل على القدرة على السداد.",
    ),
    "below_smallest": (
        "Decline: even the smallest advance is more than a typical top-up clears "
        "while leaving usable balance.",
        "رفض: حتى أصغر سلفة تتجاوز ما تسدده التعبئة المعتادة مع بقاء رصيد قابل للاستخدام.",
    ),
    "airtime_only": (
        "Advise the airtime advance only: a typical top-up clears it and leaves balance, "
        "but the 5 LYD data advance would consume the whole top-up.",
        "ننصح بسلفة الرصيد فقط: التعبئة المعتادة تسددها ويبقى رصيد، "
        "أما سلفة النت بـ 5 د.ل فتستهلك التعبئة بالكامل.",
    ),
    "both": (
        "Advise both products: a typical top-up clears either debt and still leaves balance.",
        "ننصح بالمنتجين: التعبئة المعتادة تسدد أي من السلفتين ويبقى رصيد.",
    ),
}


class AdviceError(ValueError):
    """The advice rules were given something they must refuse."""


def advance_products(market: dict) -> dict:
    """The two products as T16 recorded them, checked before anything is advised."""
    validate_market(market)
    try:
        airtime = market["airtime_advance"]
        data = market["data_advance"]
        denominations = sorted(float(value) for value in airtime["denominations_lyd"])
        price = float(data["price_lyd"])
    except (KeyError, TypeError, ValueError) as error:
        raise InvalidCatalogueError(
            "market.toml must describe both emergency credit products."
        ) from error
    if not denominations or denominations[0] <= 0:
        raise InvalidCatalogueError("The airtime advance needs positive denominations.")
    if not np.isfinite(price) or price <= 0:
        raise InvalidCatalogueError("The data advance needs a positive price.")
    return {AIRTIME: denominations, DATA: price}


def residual_after_clearing(debt_lyd: float, card_lyd: float) -> float:
    """What is left on the line after one recharge card settles a debt.

    This is the whole of the structural finding, computed rather than asserted:
    the smallest card and the data advance are both 5 LYD, so the residual is exactly zero.
    """
    return float(card_lyd) - float(debt_lyd)


def smallest_card(market: dict) -> float:
    validate_market(market)
    return min(float(value) for value in market["recharge_cards"]["values_lyd"])


def advertised_debts(market: dict) -> list[tuple[str, float]]:
    """Every debt the operator can put on a line, labelled, smallest first."""
    products = advance_products(market)
    debts = [(f"airtime advance of {value:g} LYD", value) for value in products[AIRTIME]]
    debts.append((f"data advance of {products[DATA]:g} LYD", products[DATA]))
    return debts


def zero_residual_products(market: dict) -> list[str]:
    """Which advertised debts consume the whole of the smallest recharge card.

    An exact equality is weaker evidence than an impossibility would be, so the claim this
    supports is a disincentive to recharge, never a locked door (Ali's honesty note).
    """
    card = smallest_card(market)
    return [
        label
        for label, debt in advertised_debts(market)
        if residual_after_clearing(debt, card) <= 0
    ]


def topup_by_month(frame: pd.DataFrame, rate: float) -> pd.DataFrame:
    """The average airtime top-up in each window month, in LYD.

    A month with no recharge is empty rather than zero: nothing was observed, which is not
    the same as a top-up of nothing.
    """
    months = {}
    for prefix in ("prev", "cur"):
        amount = frame[f"{prefix}_total_rech_amt"]
        count = frame[f"{prefix}_total_rech_num"]
        months[f"topup_{prefix}_lyd"] = amount.where(count > 0) / count.where(count > 0) * rate
    return pd.DataFrame(months)


def typical_topup(frame: pd.DataFrame, rate: float) -> pd.Series:
    """Each customer's habitual airtime top-up, in LYD, from the quieter window month.

    `Ali_Branch` asks for the **modal** top-up, because a mean is dragged up by one
    salary-week recharge the subscriber will not repeat.
    This dataset has no individual transactions, only monthly totals and counts, so a true
    mode cannot be computed at all.
    The nearest conservative statistic available is the average top-up in whichever of the
    two window months was quieter: it is closer to the habitual amount than an average
    across both, and it is never larger, so it cannot widen the advice.
    A month with no recharge contributes nothing, and a customer with no recharge in either
    month has no basis: unknown recharge behaviour is not evidence of capacity to repay.
    """
    return topup_by_month(frame, rate).min(axis=1, skipna=True)


def affordability_ceiling(
    typical_topup_lyd: pd.Series, fraction: float = MAX_DEBT_FRACTION
) -> pd.Series:
    """The largest debt a typical top-up can settle while still buying the customer service.

    The fraction must stay below 1.0.
    At 1.0 a debt equal to the typical top-up is permitted, which is the zero-residual case
    this ceiling exists to prevent.
    """
    if not 0.0 < fraction < 1.0:
        raise AdviceError(
            f"The debt fraction must be above 0 and below 1, not {fraction}. "
            "At 1.0 a debt equal to the typical top-up is allowed, and clearing it would "
            "return the customer to a zero balance."
        )
    return (typical_topup_lyd * fraction).fillna(0.0).clip(lower=0.0)


def airtime_limit(ceiling_lyd: pd.Series, denominations: list[float]) -> pd.Series:
    """The largest denomination the ceiling covers, or 0 to decline.

    Only amounts the operator actually sells may be advised; there is no 2 LYD advance to
    invent, so a ceiling of 2.9 LYD advises 1 LYD rather than rounding up.
    """
    rungs = np.sort(np.asarray(denominations, dtype=float))
    values = ceiling_lyd.to_numpy(dtype=float)
    position = np.searchsorted(rungs, values, side="right")
    limit = np.where(position > 0, rungs[np.clip(position - 1, 0, len(rungs) - 1)], DECLINED)
    return pd.Series(limit, index=ceiling_lyd.index, dtype=float)


def data_advance_advised(ceiling_lyd: pd.Series, price_lyd: float) -> pd.Series:
    """The data advance is flat, so the only decision available is advise or decline."""
    return ceiling_lyd >= float(price_lyd)


def advise(cleaned: pd.DataFrame, window: Window, market: dict) -> pd.DataFrame:
    """One row of advice per customer, with the reason in Arabic and English."""
    products = advance_products(market)
    frame = window_features(cleaned, window)
    by_month = topup_by_month(frame, lyd_rate(market))
    topup = by_month.min(axis=1, skipna=True)
    ceiling = affordability_ceiling(topup)
    limit = airtime_limit(ceiling, products[AIRTIME])
    data_advised = data_advance_advised(ceiling, products[DATA])

    code = pd.Series("below_smallest", index=frame.index, dtype="str")
    code = code.mask(topup.isna(), "no_recharge")
    code = code.mask(limit.gt(0) & ~data_advised, "airtime_only")
    code = code.mask(limit.gt(0) & data_advised, "both")

    return pd.DataFrame(
        {
            ID: cleaned[ID].to_numpy(),
            # Both months travel with the advice: a reviewer deciding whether to accept it
            # should see the behaviour it was read from, not only the conclusion.
            "topup_prev_lyd": by_month["topup_prev_lyd"].to_numpy(),
            "topup_cur_lyd": by_month["topup_cur_lyd"].to_numpy(),
            "typical_topup_lyd": topup.to_numpy(),
            "affordability_ceiling_lyd": ceiling.to_numpy(),
            "airtime_limit_lyd": limit.to_numpy(),
            # What the customer keeps after one typical top-up settles the advised advance.
            "airtime_residual_lyd": np.where(
                limit.to_numpy() > 0, topup.to_numpy() - limit.to_numpy(), np.nan
            ),
            "data_advance_advised": data_advised.to_numpy(),
            "advice_code": code.to_numpy(),
            "advice_reason_en": [REASONS[key][0] for key in code],
            "advice_reason_ar": [REASONS[key][1] for key in code],
        }
    )


def basis_sensitivity(advice: pd.DataFrame, market: dict) -> pd.DataFrame:
    """How much the advice depends on which statistic stands in for the modal top-up.

    The choice is an assumption, and on this base it moves the headline by twenty points,
    so it is reported beside the result rather than buried in a docstring.
    """
    products = advance_products(market)
    months = advice[["topup_prev_lyd", "topup_cur_lyd"]]
    rows = []
    for label, basis in (
        ("quieter month (used)", months.min(axis=1, skipna=True)),
        ("mean of both months", months.mean(axis=1, skipna=True)),
        ("busier month", months.max(axis=1, skipna=True)),
    ):
        ceiling = affordability_ceiling(basis)
        rows.append(
            {
                "basis": label,
                "median_topup_lyd": round(float(basis.median()), 2),
                "declined": round(float(airtime_limit(ceiling, products[AIRTIME]).eq(0).mean()), 4),
                "data_advance_advised": round(
                    float(data_advance_advised(ceiling, products[DATA]).mean()), 4
                ),
            }
        )
    return pd.DataFrame(rows)


def _share_table(advice: pd.DataFrame) -> pd.DataFrame:
    counts = advice["airtime_limit_lyd"].value_counts().sort_index()
    return pd.DataFrame(
        {
            "advised airtime limit": [
                "declined" if value == DECLINED else f"{value:g} LYD" for value in counts.index
            ],
            "customers": counts.to_numpy(),
            "share": (counts / len(advice)).round(4).to_numpy(),
        }
    )


def advice_report(advice: pd.DataFrame, market: dict, source: str) -> str:
    """The aggregate report, with every assumption beside the numbers."""
    products = advance_products(market)
    cards = sorted(float(value) for value in market["recharge_cards"]["values_lyd"])
    smallest = smallest_card(market)
    trapped = zero_residual_products(market)
    advised = advice["airtime_limit_lyd"].gt(0)
    with_basis = advice["typical_topup_lyd"].notna()

    residuals = "\n".join(
        f"| {label} | {residual_after_clearing(debt, smallest):g} LYD |"
        for label, debt in advertised_debts(market)
    )
    safe_rungs = [
        value for value in products[AIRTIME] if residual_after_clearing(value, smallest) > 0
    ]
    leftovers = " or ".join(f"{smallest - value:g}" for value in safe_rungs)
    airtime = market["airtime_advance"]
    data = market["data_advance"]
    rungs = ", ".join(f"{value:g}" for value in products[AIRTIME])
    card_values = ", ".join(f"{value:g}" for value in cards)
    floor_ceiling = MAX_DEBT_FRACTION * smallest
    floor_rung = max(value for value in products[AIRTIME] if value <= floor_ceiling)
    data_count = int(advice["data_advance_advised"].sum())
    data_share = advice["data_advance_advised"].mean()
    data_needs = products[DATA] / MAX_DEBT_FRACTION
    median_residual = advice.loc[advised, "airtime_residual_lyd"].median()
    sensitivity = "\n".join(
        f"| {row.basis} | {row.median_topup_lyd:.2f} LYD | {row.declined:.4f} "
        f"| {row.data_advance_advised:.4f} |"
        for row in basis_sensitivity(advice, market).itertuples(index=False)
    )
    median_topup = advice["typical_topup_lyd"].median()
    smallest_needs = min(products[AIRTIME]) / MAX_DEBT_FRACTION
    product_rows = "\n".join(
        [
            f"| `رصيد في وقته` airtime advance | {rungs} LYD "
            f"| balance at or below {airtime['max_balance_to_subscribe_lyd']:g} LYD "
            f"| first recharge |",
            f"| `نت في وقته` data advance | {products[DATA]:g} LYD flat, "
            f"{data['data_gb']:g} GB for {data['validity_hours']:g} hours "
            f"| balance at or below {data['max_balance_to_subscribe_lyd']:g} LYD "
            f"| first recharge or transfer |",
        ]
    )

    codes = advice["advice_code"].value_counts()
    code_rows = "\n".join(
        f"| `{code}` | {int(count)} | {count / len(advice):.4f} | {REASONS[code][0]} |"
        for code, count in codes.items()
    )
    shares = "\n".join(
        f"| {row['advised airtime limit']} | {int(row['customers'])} | {row['share']:.4f} |"
        for _, row in _share_table(advice).iterrows()
    )

    return f"""# T19 emergency credit advice

Generated by `uv run churn advance` from `{source}`.
{len(advice)} customers; {int(with_basis.sum())} of them recharged at least once in the window.
The behaviour is real upGrad prepaid data from another market; the products and the money
are the operator's (decision 16).

**This is advice, not a grant.** Nothing here subscribes anyone to anything.
A limit reaches a customer only if a person approves it, exactly as a retention offer does
(decision 14).

## The two products

Both are confirmed from the operator's own documents and recorded by T16 in
`data/operator/market.toml`.

| Product | Amount | Taken when | Recovered |
|---|---|---|---|
{product_rows}

The operator allocates the airtime denomination "according to the subscriber's
consumption" and does not publish the rule.
Consumption is not capacity to repay, which is the gap this advice fills.

## The zero-residual finding

The smallest recharge card sold is {smallest:g} LYD.

| Debt | Residual after one smallest card clears it |
|---|---|
{residuals}

Debts that consume the whole of the smallest card: {", ".join(trapped) if trapped else "none"}.

The data advance is exactly the size of the smallest card, and so is the top airtime rung.
A customer whose usual top-up is that card can clear either one and receives nothing for
doing so: the entire card goes to the debt, the line returns to a zero balance, and they
are immediately eligible to borrow again.
The smaller airtime rungs avoid this, because they leave {leftovers} LYD of usable balance
once the debt is settled.

This is why the rule below is a fraction of the top-up rather than a cap at the card value.
A customer at the recharge floor is advised {floor_ceiling:g} LYD of capacity.
That reaches the {floor_rung:g} LYD rung, not the {products[DATA]:g} LYD one, and declines the data
advance for them outright.

The harm is behavioural rather than arithmetic.
Recharging the minimum buys no service, so the rational move is to defer recharging, and a
deferred recharge on a prepaid line is indistinguishable from the start of silent churn.

An exact equality is weaker evidence than an impossibility would be.
The claim is a disincentive to recharge, not a locked door, and nothing here measures how
often it happens.

## The rule

One rule, applied to every customer:

> Never advise a debt larger than {MAX_DEBT_FRACTION:g} of the customer's typical top-up.

The fraction is below 1 deliberately.
At 1 a debt equal to the typical top-up would be allowed, which is the customer this rule
exists to protect.

| Assumption | Value | Status |
|---|---|---|
| Debt share of a typical top-up | {MAX_DEBT_FRACTION:g} | assumption, `Ali_Branch` 2026-09-18 |
| Typical top-up | average airtime recharge in the quieter window month | assumption, see below |
| LYD conversion | {lyd_rate(market):.10f} LYD per source unit | derived from the T18 ARPU |
| Recharge cards | {card_values} LYD | reported, Ali Marghem 2026-09-18 |
| Denominations advised | only {rungs} LYD | confirmed from the operator file |

`Ali_Branch` asks for the **modal** top-up, because a mean is dragged up by one
salary-week recharge that will not repeat.
This dataset holds monthly totals and counts, never individual transactions, so no mode can
be computed.
The quieter month's average is used instead: it is closer to the habitual amount than an
average across both months and never larger, so it cannot widen the advice.

### How much the basis choice matters

The statistic standing in for the mode is an assumption, and on this base it moves the
result by more than twenty points, so it is reported rather than buried.

| Basis | Median top-up | Declined | Data advance advised |
|---|---|---|---|
{sensitivity}

The conservative choice is the one used. A reader who prefers the mean should read the
middle row, and should also accept that it advises credit to customers whose quieter month
would not support it.

## What the base actually does

The decline rate below is high, and the reason is in the recharge behaviour rather than in
the rule. This base tops up **often, in very small amounts**: the median customer's typical
top-up is {median_topup:.2f} LYD.
The smallest advance needs a top-up of at least {smallest_needs:.2f} LYD at this ceiling, so a
customer who habitually adds a dinar or two at a time cannot carry even that one and still
have something left.

That is a finding about the product, not a failure of the rule.
The operator offers these advances to anyone whose balance is low enough, and on this
behaviour most of that population cannot clear the smallest one without being returned to
nothing.

## What is advised

| Advised airtime limit | Customers | Share |
|---|---|---|
{shares}

| Outcome | Customers | Share | Meaning |
|---|---|---|---|
{code_rows}

The data advance is advised for {data_count} customers, {data_share:.4f} of the base.
At a flat {products[DATA]:g} LYD it needs a top-up of at least {data_needs:.2f} LYD to clear and
leave balance.

Among the {int(advised.sum())} customers advised an airtime limit, the median balance left after
one typical top-up settles it is {median_residual:.2f} LYD.

## What this advice does not do

- **No repayment model.** No repayment outcome exists in this data, and decision 15 rules
  one out until an operator supplies repayment history. Nothing here estimates a
  probability of repayment, so no figure above is a default rate.
- **No tier, value or exposure caps.** `Ali_Branch` also caps by loyalty tier, by a share of
  customer value and by monthly cumulative exposure. Those need a repayment model, an
  advance history or a tenure tier this module does not have.
- **No chronic distress detection.** Ali's signals need balance-zero hours, failed bundle
  attempts and alternation between the two products. None of those fields exist here.
- **No cooling-off period.** That needs a history of previous advances.
- **Nothing about the other Libyan operator's credit loan.** Its tenure gate, grace period
  and line reset do not describe the operator's products and must not be quoted for them.
- **No fee.** Neither product documents one. If a fee ever appears it should be a fixed
  charge rather than time- or percentage-based, and flagged for review.
"""
