"""Screen 4 -- Campaign Builder.  Owner: E5 (engine from E4)

Filter a cohort, set an LYD budget, run the uplift simulation, see expected
retained subscribers, cost and net margin, export a targeting CSV.

The control holdout is not optional and must be visible in the UI. Without it
there is no way to isolate net margin impact, which is exactly pain point P4 --
"net margin impact is never isolated because there is no holdout group".
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _shared import base, missing_banner, synthetic_notice
from cvm.config import load_conf, settings
from cvm.decision import budget_lp

st.title("Campaign Builder")

if missing_banner(
    {
        "feature store": settings.feature_store_offline,
        "M2 CLV": settings.processed_dir / "m2_clv.parquet",
        "M3 uplift": settings.processed_dir / "m3_uplift.parquet",
    }
):
    st.stop()

frame = base()
pricing = load_conf("pricing")
market = load_conf("market")["base"]
incentive = float(market["blended_incentive_lyd"])

# --- The filter -------------------------------------------------------------
st.subheader("1. Choose a cohort")

one, two, three = st.columns(3)
with one:
    segments = st.multiselect(
        "Segments", sorted(frame["segment"].dropna().unique()), default=["At-Risk Valuable"]
    )
with two:
    min_risk = st.slider("Minimum churn probability", 0.0, 1.0, 0.05, 0.01)
with three:
    min_clv = st.slider("Minimum CLV (LYD)", 0, 2000, 100, 50)

candidates = frame.copy()
if segments:
    candidates = candidates[candidates["segment"].isin(segments)]
candidates = candidates[
    (candidates["churn_probability"].fillna(0) >= min_risk)
    & (candidates["clv_12m"].fillna(0) >= min_clv)
]

if candidates.empty:
    st.warning("No subscriber matches that filter.", icon=":material/filter_alt_off:")
    st.stop()

st.caption(f"{len(candidates):,} subscribers match, of {len(frame):,} in the base.")

# --- Guardrail rejections: the most persuasive thing on the screen ----------
st.subheader("2. What the guardrails remove")

before = len(candidates)
rejections: dict[str, int] = {}

# The blanket baseline. A blanket campaign ignores every guardrail below, so
# the comparison has to be made against the cohort as it stands HERE -- before
# the sleeping dogs, the negative expected values and the sub-ceiling CLVs come
# out. Comparing against what survives them measures targeting against itself,
# which is what this screen used to do, and it reported a saving of 0 LYD with
# the rejection chart directly above it saying 227 had been removed.
cohort = candidates.copy()

sleeping = candidates.get("quadrant", pd.Series(dtype=str)).eq("sleeping_dog")
if sleeping.any():
    rejections["Sleeping dogs — contacting them causes churn"] = int(sleeping.sum())
    candidates = candidates[~sleeping]

if "expected_value_lyd" in candidates.columns:
    negative = candidates["expected_value_lyd"].fillna(-1) <= 0
    rejections["Negative expected value — uplift x CLV below the offer cost"] = int(negative.sum())
    candidates = candidates[~negative]

below_ceiling = candidates["retention_ceiling_lyd"].fillna(0) < incentive
if below_ceiling.any():
    rejections[f"CLV ceiling — cannot justify a {incentive:.0f} LYD offer"] = int(
        below_ceiling.sum()
    )
    candidates = candidates[~below_ceiling]

held_out = candidates.get("is_control", pd.Series(False, index=candidates.index)).fillna(False)
holdout_count = int(held_out.sum())
candidates = candidates[~held_out.astype(bool)]

# Out of the baseline too: a control subscriber is treated by neither arm, so
# counting them as a blanket cost would invent a saving that targeting did not
# earn.
cohort_control = cohort.get("is_control", pd.Series(False, index=cohort.index))
cohort = cohort[~cohort_control.fillna(False).astype(bool)]

if rejections:
    rejection_frame = pd.DataFrame(
        {"reason": list(rejections), "subscribers": list(rejections.values())}
    ).sort_values("subscribers", ascending=False)
    st.plotly_chart(
        px.bar(
            rejection_frame,
            x="subscribers",
            y="reason",
            orientation="h",
            labels={"subscribers": "Removed", "reason": ""},
        ).update_layout(height=220, margin={"t": 20}),
        width="stretch",
    )
    st.caption(
        f"**{before - len(candidates) - holdout_count:,} of {before:,} removed before any "
        "money is allocated.** Every one has a stated reason. A campaign tool that cannot "
        "say who it excluded and why is one nobody should sign off."
    )
else:
    st.info("No candidate was removed by a guardrail at this filter.")

# --- The holdout, which is not optional -------------------------------------
holdout = pricing["guardrails"].get("budget", {})
st.info(
    f"**{holdout_count:,} subscribers are held out as a randomised control arm** "
    f"({load_conf('models/m3_uplift')['control_holdout_fraction']:.0%}, mandatory). Without "
    "a counterfactual there is no way to isolate net margin impact, and every ROI "
    "figure becomes an assertion. This is pain point P4.",
    icon=":material/science:",
)

if candidates.empty:
    st.warning("Every candidate was removed. Widen the filter.", icon=":material/block:")
    st.stop()

# --- The budget -------------------------------------------------------------
st.subheader("3. Set a budget")

default_budget = float(pricing["guardrails"]["budget"]["default_campaign_budget_lyd"])
budget = st.slider(
    "Campaign budget (LYD)",
    0.0,
    float(max(default_budget, len(candidates) * incentive)),
    min(default_budget, float(len(candidates) * incentive)),
    step=1000.0,
)


def _gross_margin(rows: pd.DataFrame) -> pd.Series:
    """Retained value BEFORE the discount is paid for.

    allocate() and campaign_summary() subtract the cost themselves, so handing
    them M3's `expected_value_lyd` -- which is already `uplift x CLV - cost` --
    charged the campaign twice. The screen reported 20,115 LYD of net margin on
    a cohort that returns 21,335; the missing 1,220 was the campaign cost,
    deducted once by M3 and once again here.

    Not clipped at zero either. A negative margin is a subscriber the campaign
    should not touch, and the blanket comparison exists to price exactly those.
    """
    if "uplift" in rows.columns:
        return rows["uplift"].fillna(0) * rows["clv_12m"].fillna(0)
    return rows["clv_12m"].fillna(0) * rows["churn_probability"].fillna(0)


allocation_input = candidates.assign(
    expected_margin_lyd=_gross_margin(candidates),
    discount_cost_lyd=incentive,
)
allocation = budget_lp.allocate(allocation_input, budget_lyd=budget)
summary = budget_lp.campaign_summary(
    allocation,
    cohort=cohort.assign(expected_margin_lyd=_gross_margin(cohort), discount_cost_lyd=incentive),
)

# --- The result -------------------------------------------------------------
st.subheader("4. What it buys")

a, b, c, d = st.columns(4)
a.metric("Treated", f"{summary['selected']:,}", f"of {summary['candidates']:,} eligible")
b.metric("Cost", f"{summary['cost_lyd']:,.0f} LYD", f"of {budget:,.0f} budget")
c.metric("Expected net margin", f"{summary['net_margin_lyd']:,.0f} LYD")
d.metric(
    "Worth more than spending it untargeted",
    f"{summary['net_margin_versus_same_budget_lyd']:,.0f} LYD",
    help=(
        f"The same {summary['cost_lyd']:,.0f} LYD spread across the cohort without "
        f"targeting reaches {summary['blanket_same_budget_treated']:,} subscribers and "
        f"returns {summary['blanket_same_budget_net_margin_lyd']:,.0f} LYD of net margin. "
        "Spend is held constant deliberately: comparing a budgeted campaign against an "
        "unconstrained blanket one measures the size of the budget, not the quality of "
        "the targeting, and goes negative the moment the budget binds."
    ),
)

# Two separate claims, because they answer different questions and one of them
# used to read 0 LYD. The saving is also split by cause: "a guardrail declined
# them" and "the budget ran out" are not the same event.
guardrails_saved = summary["saving_from_guardrails_lyd"]
budget_saved = summary["saving_from_budget_lyd"]
destruction_avoided = (
    summary["net_margin_versus_blanket_lyd"] - summary["saving_versus_blanket_lyd"]
)
st.caption(
    f"**Against treating all {summary['blanket_candidates']:,} in the cohort** "
    f"({summary['blanket_cost_lyd']:,.0f} LYD, netting "
    f"{summary['blanket_net_margin_lyd']:,.0f} LYD): "
    f"**{summary['saving_versus_blanket_lyd']:,.0f} LYD of discount not spent** — "
    f"{guardrails_saved:,.0f} where a guardrail declined the subscriber and "
    f"{budget_saved:,.0f} where the budget ran out before reaching them — plus "
    f"**{destruction_avoided:,.0f} LYD of expected value not destroyed** by leaving "
    "alone the people who react badly to being contacted."
)

synthetic_notice()

comparison = pd.DataFrame(
    {
        "approach": ["Targeted", "Blanket"],
        "cost_lyd": [summary["cost_lyd"], summary["blanket_cost_lyd"]],
        "net_margin_lyd": [summary["net_margin_lyd"], summary["blanket_net_margin_lyd"]],
    }
)
st.plotly_chart(
    px.bar(
        comparison,
        x="approach",
        y=["cost_lyd", "net_margin_lyd"],
        barmode="group",
        labels={"value": "LYD", "approach": "", "variable": ""},
        color_discrete_map={"cost_lyd": "#c0392b", "net_margin_lyd": "#27ae60"},
    ).update_layout(height=300, margin={"t": 20}),
    width="stretch",
)

# --- Export -----------------------------------------------------------------
st.subheader("5. Export")

selected = allocation[allocation["selected"]]
export = selected[
    [
        c
        for c in (
            "subscriber_id_hashed",
            "segment",
            "tier",
            "churn_probability",
            "clv_12m",
            "expected_margin_lyd",
        )
        if c in selected.columns
    ]
].copy()
export["offer_cost_lyd"] = incentive

st.dataframe(export.head(50), width="stretch", hide_index=True)
st.download_button(
    "Download targeting list (CSV)",
    export.to_csv(index=False).encode("utf-8"),
    file_name="cvm_campaign_targets.csv",
    mime="text/csv",
    width="stretch",
)
st.caption(
    f"{len(export):,} rows, hashed IDs only. No raw MSISDN exists anywhere in this "
    "system to export."
)
