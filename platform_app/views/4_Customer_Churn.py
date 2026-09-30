"""Embeds prepaid_churn's own tested Streamlit app - not a re-implementation.

Same reasoning as the GIS/KPI pages calling their own APIs directly: this shell
never re-implements another module's UI or logic. For churn, the module's own app
already exists and is tested, so it is embedded live via iframe (its process, its
port, its code). The summary strip above it reads churn's own `/portfolio/summary`.
"""

import streamlit as st
from _shared import unavailable
from _shared import CHURN_APP_PUBLIC_URL, CHURN_APP_URL, app_available, churn_portfolio, configure, hero

configure("Churn & Retention", icon="group")

hero(
    "Churn & Retention",
    "Which prepaid subscribers are about to leave, what they are worth, and which "
    "retention offers a named reviewer approved - from prepaid_churn's own service and app.",
    badges=["Calibrated LightGBM", "Value tiers", "Human-approved offers"],
)

with st.spinner("Loading customer summary…"):
    portfolio, portfolio_error = churn_portfolio()
if portfolio_error:
    unavailable("Customer summary unavailable", "portfolio")
else:
    bands = {band["name"]: band for band in portfolio["by_risk_band"]}
    high = bands.get("high", {})
    at_risk = sum(band.get("lyd_at_risk") or 0 for band in portfolio["by_risk_band"])
    c1, c2, c3, c4 = st.columns(4)
    with c1.container(border=True):
        st.metric("Subscribers scored", f"{portfolio['subscribers']:,}")
    with c2.container(border=True):
        st.metric("High churn risk", f"{high.get('customers', 0):,}")
    with c3.container(border=True):
        st.metric("12-month value at risk", f"{at_risk:,.0f} LYD",
                  help="Each customer's 12-month value weighted by their churn probability.")
    with c4.container(border=True):
        st.metric("Release gate", "Passed" if portfolio.get("release_gate_passed") else "Not passed",
                  help=f"Model {portfolio.get('model_version') or 'not loaded'}")

if not app_available(CHURN_APP_URL):
    unavailable("Churn workbench is offline", "churn_app")
else:
    head, link = st.columns([4, 1], vertical_alignment="bottom")
    head.subheader("Churn workbench")
    link.link_button("Open full screen", CHURN_APP_PUBLIC_URL, icon=":material/open_in_new:", width="stretch")
    st.caption("Loading the workbench below. If it stays blank, try Open full screen.")
    st.iframe(f"{CHURN_APP_PUBLIC_URL}/?embed=true&embed_options=light_theme", height=1150)
    st.caption("prepaid_churn's own app, embedded. Use its sidebar for subscribers, campaigns and approvals.")
