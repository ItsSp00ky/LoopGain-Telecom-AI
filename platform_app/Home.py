"""LoopGain Telecom AI - one landing page for four modules built on separate branches.

Run: streamlit run platform_app/Home.py

This shell does not reimplement any module. GIS and Network KPI have their own new
FastAPI services (`antenna_cell_placement/src/antenna_cell_placement/api.py`,
`network_kpi_prediction/api.py`) that this page and its two new pages call directly.
Customer Churn and the Assistants already have their own working Streamlit apps and a
key-protected FastAPI service; rather than re-import their page code into this process
(and risk drifting from their own tested behaviour), this shell links out to them as
already-running services, matching how `assistants/*_app.py` already calls churn's API
as a separate process instead of importing it.
"""

import streamlit as st
from _shared import (
    CHATBOT_APP_URL,
    CHURN_API_URL,
    CHURN_APP_URL,
    COPILOT_APP_URL,
    GIS_API_URL,
    KPI_API_URL,
    configure,
    service_status,
)

configure("Home", icon="home")

st.title("LoopGain Telecom AI")
st.caption(
    "Antenna planning, network KPI forecasting, customer churn/retention and the "
    "customer/employee assistants - built separately by team, combined here."
)

st.markdown(
    "Each module below is its own backend on its own port. This page shows whether "
    "each one is currently reachable; a module reading \"unreachable\" simply is not "
    "running yet in this environment (see `document/PLATFORM_STATUS.md` for how to "
    "start it), it is not a bug in this shell."
)

st.divider()

modules = [
    {
        "name": "GIS Antenna Planning",
        "icon": ":material/cell_tower:",
        "status_url": GIS_API_URL,
        "description": "Explainable site scoring over corrected terrain/population/road features.",
        "action": "Open the GIS Planning page in the sidebar for a live view.",
    },
    {
        "name": "Network KPI Forecast",
        "icon": ":material/monitoring:",
        "status_url": KPI_API_URL,
        "description": "4G traffic volume forecast, chronological train/val/test split, real held-out metrics.",
        "action": "Open the Network KPI page in the sidebar for a live view.",
    },
    {
        "name": "Customer Churn & Retention",
        "icon": ":material/person:",
        "status_url": CHURN_API_URL,
        "description": "Prepaid subscriber churn risk, value tiers and reviewed retention offers.",
        "action": f"[Open the Customer Churn app]({CHURN_APP_URL})",
    },
]

columns = st.columns(3)
for column, module in zip(columns, modules):
    with column:
        status, detail = service_status(module["status_url"])
        st.subheader(module["icon"] + " " + module["name"])
        st.write(module["description"])
        if status == "ok":
            st.success("Reachable", icon=":material/check_circle:")
        elif status == "unreachable":
            st.warning("Unreachable - not running in this environment", icon=":material/warning:")
        else:
            st.info(f"Status: {status}", icon=":material/info:")
        st.caption(module["action"])

st.divider()
st.subheader(":material/support_agent: Assistants")
st.write(
    "The customer chatbot and employee copilot both call the churn service directly "
    "over its key-protected API; neither is embedded in this shell for the same reason "
    "the churn app is linked rather than re-imported."
)
left, right = st.columns(2)
left.markdown(f"[Open the customer chatbot]({CHATBOT_APP_URL})")
right.markdown(f"[Open the employee copilot]({COPILOT_APP_URL})")
