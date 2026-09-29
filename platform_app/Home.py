"""LoopGain Telecom AI - one landing dashboard for four modules built on separate branches.

Run: streamlit run platform_app/Home.py (or `python3 run_platform.py` for everything)

Every number on this page comes from a real backend call - GIS's and KPI's own new
FastAPI services, and churn's existing `/portfolio/summary` (needs
PREPAID_CHURN_COPILOT_KEY, see assistants/README.md). A module that can't be reached
or hasn't been built in this checkout shows that plainly instead of a placeholder
number; see document/PLATFORM_STATUS.md for exactly what depends on what.
"""

import streamlit as st
from _shared import (
    CHURN_API_URL,
    GIS_API_URL,
    KPI_API_URL,
    churn_portfolio,
    configure,
    get_json,
    hero,
    service_status,
    status_pill,
)

configure("Dashboard", icon="hub")

hero(
    "LoopGain Telecom AI",
    "Antenna planning, network KPI forecasting, customer churn/retention and the "
    "customer/employee assistants - four modules, one operating picture.",
    badges=["GIS Planning", "KPI Forecasting", "Churn & Retention", "AI Assistants"],
)

# ---------------------------------------------------------------------------
# Real cross-module numbers, not health pings
# ---------------------------------------------------------------------------
st.subheader("Network at a glance")

gis_col, health_col, kpi_col, churn_col = st.columns(4)

with health_col:
    kpi_status, kpi_status_error = get_json(KPI_API_URL, "/kpis/status")
    if kpi_status_error:
        st.metric("Network KPI SLA breaches", "—", help=f"Unavailable: {kpi_status_error}")
    else:
        st.metric(
            "Network KPI SLA breaches",
            f"{kpi_status['breaches']} / {kpi_status['checked']}",
            help="Latest observed value of every KPI on every band, against its SLA.",
        )
        st.caption(f"As of **{kpi_status['as_of']}**, 10 KPIs x 6 bands")

with gis_col:
    with st.container():
        st.markdown('<div class="lg-metric-row">', unsafe_allow_html=True)
        shortlist, shortlist_error = get_json(GIS_API_URL, "/shortlist")
        if shortlist_error:
            st.metric("GIS shortlisted sites", "—", help=f"Unavailable: {shortlist_error}")
        else:
            features = shortlist.get("features", [])
            top_score = max((f["properties"].get("planning_priority_score", 0) for f in features), default=0)
            st.metric("GIS shortlisted sites", len(features), help="From the latest completed planning run.")
            st.caption(f"Top candidate score: **{top_score:.1f}** / 100")
        st.markdown("</div>", unsafe_allow_html=True)

with kpi_col:
    forecast, forecast_error = get_json(KPI_API_URL, "/traffic/30day", timeout=30.0)
    if forecast_error:
        st.metric("Next-day traffic forecast", "—", help=f"Unavailable: {forecast_error}")
    else:
        next_day = forecast["forecast"][0]
        st.metric(
            "Next-day traffic forecast",
            f"{next_day['predicted_kpi_volume_gb']:,.0f} GB",
            help=f"Champion model: {forecast['champion_model']}",
        )
        st.caption(f"Held-out test WAPE: **{forecast['test_metrics']['WAPE (%)']:.2f}%**")

with churn_col:
    portfolio, portfolio_error = churn_portfolio()
    if portfolio_error:
        st.metric("Subscribers monitored", "—", help=f"Unavailable: {portfolio_error}")
    else:
        at_risk = sum(band.get("lyd_at_risk") or 0 for band in portfolio["by_risk_band"])
        st.metric("Subscribers monitored", f"{portfolio['subscribers']:,}")
        st.caption(f"Revenue at risk: **{at_risk:,.0f} LYD** (model `{portfolio['model_version']}`)")

st.divider()

# ---------------------------------------------------------------------------
# Module cards
# ---------------------------------------------------------------------------
st.subheader("Modules")

modules = [
    {
        "name": "GIS Antenna Planning",
        "icon": "cell_tower",
        "status_url": GIS_API_URL,
        "description": "Explainable site scoring over corrected terrain/population/road features.",
        "page": "pages/1_GIS_Planning.py",
        "page_label": "Open GIS Planning",
    },
    {
        "name": "Network KPI Forecast",
        "icon": "monitoring",
        "status_url": KPI_API_URL,
        "description": "All 10 radio KPIs on 6 bands: live SLA health, forecasts with accuracy flags, 4G traffic.",
        "page": "pages/2_Network_KPI.py",
        "page_label": "Open Network KPI",
    },
    {
        "name": "Customer Churn & Retention",
        "icon": "person",
        "status_url": CHURN_API_URL,
        "description": "Prepaid subscriber churn risk, value tiers and reviewed retention offers.",
        "page": "pages/3_Customer_Churn.py",
        "page_label": "Open Customer Churn",
    },
    {
        "name": "AI Assistants",
        "icon": "support_agent",
        "status_url": CHURN_API_URL,
        "description": "Customer chatbot and employee copilot, grounded only in the churn service.",
        "page": "pages/4_Assistants.py",
        "page_label": "Open Assistants",
    },
]

columns = st.columns(4)
for column, module in zip(columns, modules):
    with column:
        status, _ = service_status(module["status_url"])
        st.markdown(
            f"""
            <div class="lg-card">
                <h3>:material/{module['icon']}: {module['name']}</h3>
                {status_pill(status)}
                <p class="lg-desc" style="margin-top:0.6rem;">{module['description']}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.page_link(module["page"], label=module["page_label"], icon=":material/arrow_forward:")

st.divider()
st.caption(
    "GIS and KPI pages call their own FastAPI services directly. The Customer Churn "
    "and Assistants pages embed each module's own already-running Streamlit app - "
    "same tested code, one shell. See document/PLATFORM_STATUS.md for exactly what's "
    "wired versus still a standalone module."
)
