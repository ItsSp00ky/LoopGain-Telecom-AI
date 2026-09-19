"""Screen 1 -- Executive Overview.  Owner: E5

Subscribers at risk (30d), revenue at risk in LYD, base composition by tier,
churn trend, and a retained-revenue simulation against a do-nothing baseline.

The do-nothing baseline is the point of the screen: it is what turns a model
metric into a number an executive can act on.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _shared import base, missing_banner, report, synthetic_notice
from cvm.config import load_conf, settings

st.title("Executive Overview")

if missing_banner(
    {
        "feature store": settings.feature_store_offline,
        "M1 scores": settings.processed_dir / "m1_scores.parquet",
        "M2 CLV": settings.processed_dir / "m2_clv.parquet",
    }
):
    st.stop()

frame = base()
market = load_conf("market")["base"]

# --- The headline -----------------------------------------------------------
#
# REVENUE AT RISK IS CLV WEIGHTED BY PROBABILITY, not the CLV of everyone in the
# top deciles. 3,500 subscribers at 22% risk is not 3,500 lifetimes of revenue
# at risk, and quoting it that way would overstate the headline roughly fivefold
# -- in the flattering direction, which is exactly when to be careful.
at_risk = frame[frame["risk_decile"] <= 3]
revenue_at_risk = float((frame["clv_12m"] * frame["churn_probability"]).sum())
expected_churners = float(frame["churn_probability"].sum())

left, middle, right = st.columns(3)
left.metric(
    "Expected churners (30d)",
    f"{expected_churners:,.0f}",
    help=(
        "The SUM of calibrated probabilities, not a count above a threshold. "
        "Calibration is what makes that sum meaningful."
    ),
)
middle.metric(
    "Revenue at risk",
    f"{revenue_at_risk:,.0f} LYD",
    help="Each subscriber's 12-month CLV weighted by their churn probability.",
)
ceiling = float(frame["retention_ceiling_lyd"].sum()) if "retention_ceiling_lyd" in frame else 0.0
right.metric(
    "Total retention budget available",
    f"{ceiling:,.0f} LYD",
    help=(
        f"{load_conf('pricing')['guardrails']['clv_ceiling']['max_fraction_of_clv']:.0%} of CLV "
        "per subscriber -- the CFO-facing ceiling, summed over the base."
    ),
)

synthetic_notice()
st.divider()

# --- The do-nothing baseline ------------------------------------------------
st.subheader("Against doing nothing")
st.markdown(
    "A model metric becomes an executive number only when it is compared with "
    "the alternative. Below: what the base is worth if nobody intervenes, "
    "against what a targeted campaign would retain."
)

uplift_report = report("m3_uplift.json") or {}
criteo = uplift_report.get("criteo_validation", {})
realised_uplift = float(criteo.get("uplift_at_k", 0.0))
incentive = float(market["blended_incentive_lyd"])

targeted = frame[
    (frame["risk_decile"] <= 3) & (frame.get("quadrant", "persuadable") == "persuadable")
]
if targeted.empty:
    targeted = frame[frame["risk_decile"] <= 3]

retained = float(len(targeted) * realised_uplift)
retained_value = retained * float(frame["clv_12m"].median())
campaign_cost = float(len(targeted) * incentive)

comparison = pd.DataFrame(
    {
        "scenario": ["Do nothing", "Targeted campaign", "Blanket campaign"],
        "cost_lyd": [0.0, campaign_cost, float(len(frame) * incentive)],
        "retained_value_lyd": [0.0, retained_value, retained_value],
    }
)
comparison["net_lyd"] = comparison["retained_value_lyd"] - comparison["cost_lyd"]

chart = px.bar(
    comparison,
    x="scenario",
    y=["cost_lyd", "retained_value_lyd"],
    barmode="group",
    labels={"value": "LYD", "scenario": "", "variable": ""},
    color_discrete_map={"cost_lyd": "#c0392b", "retained_value_lyd": "#27ae60"},
)
chart.update_layout(height=320, margin={"t": 20, "b": 20})
st.plotly_chart(chart, width="stretch")

st.dataframe(
    comparison.style.format(
        {"cost_lyd": "{:,.0f}", "retained_value_lyd": "{:,.0f}", "net_lyd": "{:,.0f}"}
    ),
    width="stretch",
    hide_index=True,
)

if criteo:
    st.caption(
        f"Uplift of **{100 * realised_uplift:.2f} pp** is the figure measured on "
        f"Criteo's real randomised arms at the top {criteo.get('k', 0.3):.0%} — not a "
        "number taken from this generated population. The blanket row assumes the "
        "same retention for a campaign across the whole base, which is the "
        "optimistic reading of it."
    )
else:
    st.warning("M3 has not been run, so the uplift figure is zero.", icon=":material/warning:")

st.divider()

# --- Composition ------------------------------------------------------------
st.subheader("Where the risk sits")
one, two = st.columns(2)

with one:
    by_tier = (
        frame.groupby("tier")
        .agg(subscribers=("subscriber_id_hashed", "size"), at_risk=("churn_probability", "sum"))
        .reset_index()
    )
    by_tier["risk_share"] = by_tier["at_risk"] / by_tier["subscribers"]
    st.plotly_chart(
        px.bar(
            by_tier.sort_values("subscribers"),
            x="subscribers",
            y="tier",
            orientation="h",
            color="risk_share",
            color_continuous_scale="Reds",
            labels={"subscribers": "Subscribers", "tier": "", "risk_share": "Mean risk"},
            title="Base by tier, shaded by mean churn risk",
        ).update_layout(height=320, margin={"t": 40}),
        width="stretch",
    )

with two:
    by_segment = (
        frame.groupby("segment")
        .agg(subscribers=("subscriber_id_hashed", "size"), value=("clv_12m", "sum"))
        .reset_index()
        .sort_values("value", ascending=False)
    )
    st.plotly_chart(
        px.bar(
            by_segment,
            x="value",
            y="segment",
            orientation="h",
            labels={"value": "Total CLV (LYD)", "segment": ""},
            title="Value by RFM-LE segment",
        ).update_layout(height=320, margin={"t": 40}),
        width="stretch",
    )

st.subheader("Risk distribution")
st.plotly_chart(
    px.histogram(
        frame,
        x="churn_probability",
        nbins=60,
        labels={"churn_probability": "Calibrated churn probability"},
    ).update_layout(height=280, margin={"t": 20}, yaxis_title="Subscribers"),
    width="stretch",
)
st.caption(
    f"Mean {frame['churn_probability'].mean():.4f} against a generated base rate of "
    f"{market['monthly_silent_churn_rate']:.4f}. A calibrated model's mean prediction "
    "should sit on the base rate; that it does is the check, not a coincidence."
)
