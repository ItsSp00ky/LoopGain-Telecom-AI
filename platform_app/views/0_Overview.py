"""Overview: the operator's morning briefing across every module.

Every number comes from a real backend call - GIS and network APIs, and churn's
existing `/portfolio/summary` (needs PREPAID_CHURN_COPILOT_KEY, see
assistants/README.md). A module that can't be reached, or hasn't been built in this
checkout, says so instead of showing a placeholder number.
"""

import streamlit as st
from _shared import (
    CHATBOT_APP_URL,
    CHURN_API_URL,
    COPILOT_APP_URL,
    GIS_API_URL,
    KPI_API_URL,
    app_reachable,
    churn_portfolio,
    configure,
    get_json,
    groq_key_configured,
    hero,
    service_status,
    status_pill,
)

configure("Overview", icon="dashboard")

hero(
    "LoopGain Telecom AI",
    "One operating picture for a mobile operator: how the network is performing, where it "
    "is congested, where to build next, and which customers are about to leave.",
    badges=["Network KPIs", "Congestion & steering", "Site planning", "Churn & retention", "AI assistants"],
)

shortlist, shortlist_error = get_json(GIS_API_URL, "/shortlist")
kpi_status, kpi_error = get_json(KPI_API_URL, "/kpis/status")
steering, steering_error = get_json(KPI_API_URL, "/steering/summary", timeout=15.0)
traffic, traffic_error = get_json(KPI_API_URL, "/traffic/30day", timeout=30.0)
portfolio, portfolio_error = churn_portfolio()


def tile(column, label, value, note, help_text=None):
    with column.container(border=True, height=158):
        st.metric(label, value, help=help_text)
        st.markdown(f'<span class="lg-muted">{note}</span>', unsafe_allow_html=True)


def unavailable(error):
    return f"Unavailable: {error.split(':')[0]}" if error else ""


# ---------------------------------------------------------------------------
t1, t2, t3, t4, t5 = st.columns(5)

if kpi_error:
    tile(t1, "KPI SLA breaches", "—", unavailable(kpi_error))
else:
    tile(t1, "KPI SLA breaches", f"{kpi_status['breaches']} / {kpi_status['checked']}",
         f"10 KPIs × 6 bands, {kpi_status['as_of']}")

if steering_error:
    tile(t2, "Critical towers", "—", unavailable(steering_error))
else:
    critical = steering["latest_day"]["alerts_by_category"].get("CRITICAL", 0)
    tile(t2, "Critical towers", f"{critical}",
         f"{steering['latest_day']['recommendations']} steering proposals, {steering['window_end']}")

if traffic_error:
    tile(t3, "Next-day 4G traffic", "—", unavailable(traffic_error))
else:
    next_day = traffic["forecast"][0]
    tile(t3, "Next-day 4G traffic", f"{next_day['predicted_kpi_volume_gb'] / 1e6:,.2f} PB",
         f"Held-out error {traffic['test_metrics']['WAPE (%)']:.1f}% WAPE",
         help_text=f"{next_day['predicted_kpi_volume_gb']:,.0f} GB forecast for {next_day['date']}")

if shortlist_error:
    tile(t4, "Candidate sites", "—", unavailable(shortlist_error))
else:
    features = shortlist.get("features", [])
    top = max((f["properties"].get("planning_priority_score", 0) for f in features), default=0)
    tile(t4, "Candidate sites", f"{len(features)}", f"For engineering review, top score {top:.0f}/100")

if portfolio_error:
    tile(t5, "Revenue at risk", "—", unavailable(portfolio_error))
else:
    at_risk = sum(band.get("lyd_at_risk") or 0 for band in portfolio["by_risk_band"])
    tile(t5, "Revenue at risk", f"{at_risk / 1000:,.0f}k LYD",
         f"Across {portfolio['subscribers']:,} prepaid subscribers",
         help_text="12-month value weighted by each customer's churn probability.")

# ---------------------------------------------------------------------------
left, right = st.columns([3, 2], gap="large")

with left:
    st.subheader("Needs attention")
    items = []
    if not kpi_error:
        rows = kpi_status["status"]
        availability = sum(1 for r in rows if r["kpi"] == "availability_pct" and r["sla_met"] is False)
        bands = len({r["band"] for r in rows})
        items.append(("#e0533d", f"{kpi_status['breaches']}",
                      f"KPI readings breach SLA - availability is under 99.5% on {availability} of {bands} bands.",
                      "views/2_Network_KPI.py", "Network KPIs"))
    if not steering_error:
        latest = steering["latest_day"]
        items.append(("#e0533d", f"{latest['alerts_by_category'].get('CRITICAL', 0)}",
                      f"towers critically congested on {steering['window_end']}, "
                      f"{latest['recommendations']} handover-offset changes proposed.",
                      "views/3_Congestion_Steering.py", "Congestion"))
    if not portfolio_error:
        high = next((b for b in portfolio["by_risk_band"] if b["name"] == "high"), None)
        if high:
            items.append(("#f0a63c", f"{high['customers']:,}",
                          f"subscribers at high churn risk, {high['lyd_at_risk']:,.0f} LYD of 12-month value.",
                          "views/4_Customer_Churn.py", "Churn"))
    if not shortlist_error:
        items.append(("#1454a3", f"{len(shortlist.get('features', []))}",
                      "candidate cell sites ranked and waiting for engineering review.",
                      "views/1_GIS_Planning.py", "Site planning"))

    with st.container(border=True):
        if not items:
            st.info("No module is reachable yet - start the platform with `python3 run_platform.py`.")
        for colour, number, text, page, label in items:
            row_text, row_link = st.columns([5, 1], vertical_alignment="center")
            row_text.markdown(
                f'<div class="lg-alert"><span class="lg-dot" style="background:{colour}"></span>'
                f"<b>{number}</b><span>{text}</span></div>",
                unsafe_allow_html=True,
            )
            row_link.page_link(page, label="Open", icon=":material/arrow_forward:", help=f"Go to {label}")

with right:
    st.subheader("Platform status")
    gis_status, _ = service_status(GIS_API_URL)
    kpi_health, _ = service_status(KPI_API_URL)
    churn_health, _ = service_status(CHURN_API_URL)
    assistants_up = [app_reachable(CHATBOT_APP_URL), app_reachable(COPILOT_APP_URL)]
    assistants_status = "ok" if all(assistants_up) else ("degraded" if any(assistants_up) else "unreachable")

    modules = [
        ("Network KPI service", kpi_health, "10 KPIs × 6 bands, traffic, towers, steering"),
        ("GIS planning service", gis_status,
         "Shortlist and map live; point assessment needs local source data"
         if gis_status == "degraded" else "Shortlist, map and point assessment"),
        ("Churn service", churn_health, "Scores, value tiers, approved offers"),
        ("Chatbot and copilot", assistants_status,
         "Conversation on (Groq key configured)" if groq_key_configured()
         else "Conversation off: no GROQ_API_KEY configured"),
    ]
    with st.container(border=True):
        for name, status, note in modules:
            st.markdown(
                f"{status_pill(status)} &nbsp;**{name}**<br><span class='lg-muted'>{note}</span>",
                unsafe_allow_html=True,
            )

st.caption(
    "Every figure is read live from each module's own service or outputs. Network "
    "congestion and steering are a backtest over held-out days, not live network orders. "
    "See document/PLATFORM_STATUS.md for what each page relies on."
)
