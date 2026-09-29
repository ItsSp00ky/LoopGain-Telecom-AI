"""Screen 1 - Overview: customers and LYD at risk, and what the model was allowed on."""

import pandas as pd
import streamlit as st
from _shared import configure, degraded_notice, expected, lyd, missing_banner, ordered_bar, state

from prepaid_churn.demo import (
    RISK_BANDS,
    VALUE_TIERS,
    expected_churners,
    group_counts,
    revenue_at_risk,
)


def readable(groups: pd.DataFrame) -> pd.DataFrame:
    """Round the money for the screen; the underlying figures are untouched."""
    shown = groups.copy()
    for column in ("monthly_spend_lyd", "lyd_at_risk"):
        shown[column] = shown[column].astype(float).round(2)
    return shown


configure("Overview", icon="monitoring")
demo = state()

st.title("Overview")

if missing_banner(demo, ("portfolio",)):
    st.stop()

degraded_notice(demo)
portfolio = demo.portfolio

left, middle, right = st.columns(3)
left.metric("Customers", f"{len(portfolio):,}")
churners = expected_churners(portfolio)
middle.metric("Expected churners next month", expected(churners))
right.metric("Revenue at risk", lyd(revenue_at_risk(portfolio)))

st.divider()

# --- By risk band and value tier --------------------------------------------
bands = group_counts(portfolio, "risk_band", RISK_BANDS)
tiers = group_counts(portfolio, "value_tier", VALUE_TIERS)

risk_column, tier_column = st.columns(2)

with risk_column:
    st.subheader("By risk band")
    if bands.empty:
        st.info(
            "No risk band in this export. Score the base with a gated bundle "
            "(`uv run churn tiers`) to fill this.",
            icon=":material/info:",
        )
    else:
        st.altair_chart(ordered_bar(bands, RISK_BANDS), width="stretch")
        st.dataframe(readable(bands), width="stretch", hide_index=True)

with tier_column:
    st.subheader("By value tier")
    st.altair_chart(ordered_bar(tiers, VALUE_TIERS), width="stretch")
    st.dataframe(readable(tiers), width="stretch", hide_index=True)

st.caption(
    "`lyd_at_risk` is the 12-month value weighted by each customer's churn probability, "
    "so it is an expected loss under the T10 assumptions. It is blank, not zero, when "
    "this export carries no risk estimate. `monthly_spend_lyd` is the assumed recharge "
    "at the frozen T18 rate, not observed operator revenue."
)

st.divider()

# --- The model and what it was allowed on -----------------------------------
st.subheader("The model behind these numbers")

gate = demo.service.release_gate
if gate is None:
    st.info(
        "No bundle is loaded, so there are no test results to show. Run `uv run churn bundle`.",
        icon=":material/info:",
    )
else:
    st.markdown(f"Bundle `{demo.model_version}`, champion `{gate['champion']}`.")
    checks = pd.DataFrame(
        [
            {
                "check": name,
                "what it measures": check["description"],
                "value": round(float(check["value"]), 4),
                "required": check["required"],
                "passed": "yes" if check["passed"] else "no",
            }
            for name, check in gate["thresholds"].items()
        ]
    )
    st.dataframe(checks, width="stretch", hide_index=True)
    st.caption(
        "The four success thresholds of decision 13, measured once on the frozen test "
        "window. The test window is spent: no model, feature or threshold may change "
        "because of these numbers."
    )

    metrics = pd.DataFrame(gate["test_metrics"]).T.reset_index(names="model")
    st.dataframe(metrics, width="stretch", hide_index=True)
