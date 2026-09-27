"""Demo app for the prepaid customer module (ticket T14).

Five screens, in `app/pages/`; Streamlit orders them by filename.

    1  Overview           customers and LYD at risk by risk band and value tier
    2  Subscriber         one customer: risk, reasons, tier, bundle held, credit, offer
    3  Campaign builder   budget, holdout, cost and value, then named approval
    4  Message preview    the Arabic text an approved customer would receive
    5  Released           the approved offers, who approved them and where they are served

Run: uv run streamlit run app/Home.py
"""

import streamlit as st
from _shared import CAPTION, configure, degraded_notice, expected, lyd, state

from prepaid_churn.demo import expected_churners, revenue_at_risk
from prepaid_churn.operator_market import load_market

configure("Home", icon="home")
demo = state()

st.title("Prepaid customer module")
st.caption(CAPTION)

st.markdown(
    """
    Churn risk, value tiers and retention offers for prepaid subscribers, shown in
    operator packages and Libyan dinar.

    Every figure on these screens comes from a file the pipeline wrote.
    Nothing here trains a model, scores a customer or chooses an offer, and no offer
    reaches a customer until a named reviewer approves it.

    Pick a screen from the sidebar.
    """
)

degraded_notice(demo)

portfolio = demo.portfolio
churners = expected_churners(portfolio)
at_risk = revenue_at_risk(portfolio)

left, middle, right = st.columns(3)
left.metric(
    "Customers in the base",
    f"{0 if portfolio is None else len(portfolio):,}",
    help="Rows in the latest `churn tiers` export.",
)
middle.metric(
    "Expected churners next month",
    expected(churners),
    help=(
        "The sum of calibrated probabilities, not a count above a threshold. "
        "Calibration is what makes that sum mean anything."
    ),
)
right.metric(
    "Revenue at risk",
    lyd(at_risk),
    help=(
        "Each customer's 12-month value weighted by their own churn probability, under "
        "the T10 scenario assumptions. Not the value of everyone in a risky band."
    ),
)

st.divider()

model_version = demo.model_version
if model_version:
    st.success(f"Serving model bundle `{model_version}`.", icon=":material/verified:")
else:
    st.info(
        "No model bundle is loaded, so the screens show tiers, spend and the catalogue only.",
        icon=":material/info:",
    )

if demo.missing:
    st.subheader("Not built yet in this checkout")
    for what, how in demo.missing:
        st.markdown(f"- **{what}** - run `{how}`")

st.divider()
st.caption(
    "The upGrad prepaid dataset is educational and from another market, so no figure "
    "here is evidence of performance for the operator. Money is shown at the assumed "
    f"{load_market()['arpu']['monthly_lyd']:.0f} LYD monthly ARPU of T18 (decision 42), "
    "which is an assumption and not an operator figure."
)
