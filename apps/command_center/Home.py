"""CVM Command Center -- operator-facing console.  Owner: E5

Six screens, in apps/command_center/pages/. Streamlit numbers them by filename.

    1  Executive Overview   subscribers at risk, revenue at risk in LYD
    2  Segment Explorer     RFM-LE heatmap, dendrogram, PCA scatter
    3  Subscriber 360       the demo centrepiece
    4  Campaign Builder     cohort -> budget -> uplift sim -> export

Run:  streamlit run apps/command_center/Home.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _shared import base, report
from cvm.config import settings

st.set_page_config(
    page_title="AI CVM Suite -- Command Center",
    page_icon="signal_strength",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("AI CVM Suite -- Command Center")
st.caption(
    "Samsung Innovation Campus Libya 2026  |  Almadar Aljadid — المدار الجديد (MCC/MNC 606-01)"
)

st.markdown("""
    A decision-intelligence layer over prepaid telemetry. Four outputs per
    subscriber: a calibrated silent-churn probability, a value and loyalty
    tier, a margin-constrained priced offer, and a personalised airtime
    advance limit.

    Pick a screen from the sidebar.
    """)

# A PARTIAL DEPLOY MUST BE VISIBLE. Stale numbers with no banner are worse than
# no numbers: during a demo nobody checks whether the pipeline ran, and a
# dashboard reading a three-day-old parquet looks exactly like one reading a
# fresh one.
required = {
    "feature store": settings.feature_store_offline,
    "M1 scores": settings.processed_dir / "m1_scores.parquet",
    "M2 CLV": settings.processed_dir / "m2_clv.parquet",
    "M4 advances": settings.processed_dir / "m4_advance.parquet",
}
absent = {name: path for name, path in required.items() if not path.exists()}

if absent:
    st.error(
        "**Running degraded.** These pipeline outputs are missing, so the figures "
        "below are incomplete:\n\n"
        + "\n".join(f"- {name} (`{path.name}`)" for name, path in absent.items()),
        icon=":material/error:",
    )
    col1, col2, col3 = st.columns(3)
    col1.metric("Expected churners (30d)", "--")
    col2.metric("Revenue at risk", "-- LYD")
    col3.metric("Unclearable debts avoided", "--")
else:
    frame = base()
    expected = float(frame["churn_probability"].sum())
    revenue = float((frame["clv_12m"] * frame["churn_probability"]).sum())

    advances = report("m4_advance.json") or {}
    declined = sum(
        product.get("binding_constraints", {}).get("affordability_ceiling", 0)
        for product in advances.get("by_product", {}).values()
    )

    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Expected churners (30d)",
        f"{expected:,.0f}",
        help=(
            "The SUM of calibrated probabilities, not a count above a threshold. "
            "Calibration is what makes that sum mean anything."
        ),
    )
    col2.metric(
        "Revenue at risk",
        f"{revenue:,.0f} LYD",
        help="Each subscriber's 12-month CLV weighted by their churn probability.",
    )
    col3.metric(
        "Unclearable debts avoided",
        f"{declined:,}",
        help=(
            "M4: emergency advances declined because the debt would have consumed a "
            "whole typical top-up, returning the subscriber to zero. The recharge then "
            "buys them nothing, and the rational move is to defer it — which is where "
            "silent churn starts."
        ),
    )

st.divider()
st.info(
    "Metrics are computed from generated data. Synthetic metrics are not "
    "evidence of production performance -- see the technical report for the "
    "real-data validation path required before any deployment decision.",
    icon=":material/info:",
)
