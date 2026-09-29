"""Embeds prepaid_churn's own tested Streamlit app - not a re-implementation.

Same reasoning as the GIS/KPI pages calling their own APIs directly: this shell
never re-implements another module's UI or logic. For churn, the module's own app
already exists and is tested, so it is embedded live via iframe (its process, its
port, its code) rather than copied into this shell or linked out to a new tab.
"""

import streamlit as st
from _shared import CHURN_APP_URL, app_reachable, configure, hero

configure("Customer Churn", icon="person")

hero(
    "Customer Churn & Retention",
    "Prepaid subscriber churn risk, value tiers and reviewed retention offers, "
    "served live from prepaid_churn's own app.",
)

if not app_reachable(CHURN_APP_URL):
    st.warning(
        f"The churn app isn't reachable at {CHURN_APP_URL} yet. Start it with "
        "`python3 run_platform.py` after setting `PREPAID_CHURN_CHATBOT_KEY` and "
        "`PREPAID_CHURN_COPILOT_KEY` (see assistants/README.md), or run it directly "
        "from `prepaid_churn/` with `uv run streamlit run app/Home.py --server.port 8501`."
    )
else:
    st.iframe(CHURN_APP_URL, height=1000)
