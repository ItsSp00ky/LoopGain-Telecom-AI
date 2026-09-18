"""CVM Command Center -- operator-facing console.  Owner: E5

Six screens, in apps/command_center/pages/. Streamlit numbers them by filename.

    1  Executive Overview   subscribers at risk, revenue at risk in LYD
    2  Segment Explorer     RFM-LE heatmap, dendrogram, PCA scatter
    3  Subscriber 360       the demo centrepiece
    4  Campaign Builder     cohort -> budget -> uplift sim -> export

Run:  streamlit run apps/command_center/Home.py
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="AI CVM Suite -- Command Center",
    page_icon="signal_strength",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("AI CVM Suite -- Command Center")
st.caption("Samsung Innovation Campus Libya 2026  |  Almadar Aljadid — المدار الجديد (MCC/MNC 606-01)")

st.markdown(
    """
    A decision-intelligence layer over prepaid telemetry. Four outputs per
    subscriber: a calibrated silent-churn probability, a value and loyalty
    tier, a margin-constrained priced offer, and a personalised airtime
    advance limit.

    Pick a screen from the sidebar.
    """
)

col1, col2, col3 = st.columns(3)
col1.metric("Subscribers at risk (30d)", "--", help="M1, calibrated probability, top 3 deciles")
col2.metric("Revenue at risk", "-- LYD", help="At-risk subscribers weighted by predicted CLV")
col3.metric(
    "Unclearable debts avoided",
    "--",
    help=(
        "M4: emergency advances declined or stepped down because the debt would "
        "have exceeded what one typical top-up clears. Unpaid debt blocks "
        "re-subscription, locking the subscriber out of the service."
    ),
)

st.divider()
st.info(
    "Metrics are computed from generated data. Synthetic metrics are not "
    "evidence of production performance -- see the technical report for the "
    "real-data validation path required before any deployment decision.",
    icon=":material/info:",
)

# TODO(E5): read from the API via cvm.config.settings.api_url; show a clear
# banner when /health reports "degraded" so a partial deploy is visible during
# the demo rather than silently showing stale numbers.