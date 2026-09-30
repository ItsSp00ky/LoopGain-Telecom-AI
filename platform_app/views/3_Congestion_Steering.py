"""Tower congestion and traffic steering, from tower_kpi_forecast + traffic_steering_son.

Read-only. The per-tower forecasts are next-day predictions over held-out days, and
steering runs on those, so every recommendation here is what would have been
recommended on that day - a backtest, not a live order sent to the network.
"""

import altair as alt
import pandas as pd
import streamlit as st
from _shared import KPI_API_URL, configure, get_json, hero

configure("Congestion & Steering", icon="alt_route")

hero(
    "Congestion & Traffic Steering",
    "Per-tower XGBoost forecasts of load, speed, availability and drops feed a congestion "
    "detector, which proposes 3GPP handover-offset (CIO) changes to move users from "
    "overloaded towers to neighbours with headroom.",
    badges=["1,067 towers", "4 tower KPIs", "CIO load balancing"],
)

summary, error = get_json(KPI_API_URL, "/steering/summary", timeout=15.0)
if error:
    st.error(f"Steering data unavailable from {KPI_API_URL}: {error}")
    st.stop()

st.info(
    f"Backtest window **{summary['window_start']} to {summary['window_end']}**: the "
    "forecasts are next-day predictions on held-out days, and the recommendations are what "
    "the system would have proposed each day. Nothing here is sent to the network.",
    icon=":material/history:",
)

latest = summary["latest_day"]
a1, a2, a3, a4 = st.columns(4)
for column, label, value in [
    (a1, "Critical towers, latest day", latest["alerts_by_category"].get("CRITICAL", 0)),
    (a2, "High-risk towers, latest day", latest["alerts_by_category"].get("HIGH", 0)),
    (a3, "Steering proposals, latest day", latest["recommendations"]),
    (a4, "Towers alerted in the window", summary["towers_with_alerts"]),
]:
    with column.container(border=True):
        st.metric(label, f"{value:,}")

recs_tab, clusters_tab, tower_tab = st.tabs([
    ":material/alt_route: Steering recommendations",
    ":material/hub: Cluster capacity",
    ":material/cell_tower: Tower forecast check",
])

with recs_tab:
    left, right = st.columns([1, 3], vertical_alignment="bottom")
    priority = left.selectbox("Change size", ["All", "HIGH", "MEDIUM", "LOW"],
                              help="HIGH moves 10+ users (+3 dB), MEDIUM 6-9 (+2 dB), LOW up to 5 (+1 dB).")
    query = "/steering/recommendations?limit=200" + ("" if priority == "All" else f"&priority={priority}")
    recs, recs_error = get_json(KPI_API_URL, query, timeout=15.0)
    if recs_error:
        st.error(f"Recommendations unavailable: {recs_error}")
    else:
        shown = f"top {recs['count']} of {recs['total']}" if recs["count"] < recs["total"] else f"all {recs['total']}"
        right.caption(f"Showing {shown} proposals for {recs['date']}, most congested towers first.")
        frame = pd.DataFrame(recs["recommendations"])
        if frame.empty:
            st.info("No recommendations at this priority on the latest day.")
        else:
            offset = frame["Recommended_3GPP_Action"].str.extract(r"([+-]\d+ dB)", expand=False).fillna("")
            frame["change"] = "CIO " + offset + " → " + frame["Acceptor_Original_Name"]
            st.dataframe(
                frame[[
                    "Risk_Score", "Donor_Original_Name", "Cluster", "change",
                    "Users_To_Offload", "Donor_Current_Users",
                    "Donor_Current_Speed_Mbps", "Estimated_Donor_Speed_After",
                    "Predicted_QoE_Boost", "Priority",
                ]],
                column_config={
                    "Risk_Score": st.column_config.ProgressColumn(
                        "Congestion risk", min_value=0, max_value=100, format="%.0f", width="small"),
                    "Donor_Original_Name": st.column_config.TextColumn("Tower", width="small", help="The congested tower users are moved away from."),
                    "Cluster": st.column_config.TextColumn("Cluster", width="small"),
                    "change": st.column_config.TextColumn(
                        "Proposed change", width="medium",
                        help="3GPP Cell Individual Offset raised towards the named neighbour, so it takes the users."),
                    "Users_To_Offload": st.column_config.NumberColumn("To move", width="small", help="Users the change moves to the neighbour."),
                    "Donor_Current_Users": st.column_config.NumberColumn("Users now", format="%.1f", width="small"),
                    "Donor_Current_Speed_Mbps": st.column_config.NumberColumn("Speed now", format="%.2f Mbps"),
                    "Estimated_Donor_Speed_After": st.column_config.NumberColumn("Speed after (est.)", format="%.2f Mbps"),
                    "Predicted_QoE_Boost": st.column_config.TextColumn("Speed gain (est.)"),
                    "Priority": st.column_config.TextColumn("Change size", width="small"),
                },
                hide_index=True, width="stretch", height=460,
            )
        st.caption(
            "\"Change size\" is how many users a proposal moves, not how urgent it is - "
            "urgency is the congestion risk, which is why a small (+1 dB) change can top the "
            "list. The speed figures are arithmetic, not measurements: they assume the "
            "tower's capacity is shared equally, so moving users raises the remaining users' "
            "speed in proportion. Real gains depend on radio conditions this does not model."
        )
    totals = summary["recommendations_by_priority"]
    st.caption(
        f"Whole window: {totals.get('HIGH', 0):,} high, {totals.get('MEDIUM', 0):,} medium, "
        f"{totals.get('LOW', 0):,} low-priority recommendations."
    )

with clusters_tab:
    clusters, clusters_error = get_json(KPI_API_URL, "/steering/clusters")
    if clusters_error:
        st.error(f"Cluster capacity unavailable: {clusters_error}")
    else:
        frame = pd.DataFrame(clusters["clusters"])
        chart = (
            alt.Chart(frame)
            .mark_bar(color="#1454a3")
            .encode(
                x=alt.X("Avg_Congestion_Risk:Q", title="Average congestion risk (0-100)"),
                y=alt.Y("Cluster:N", sort="-x", title=None),
                tooltip=["Cluster", "Total_Towers", "Avg_Users_Per_Tower", "Peak_Tower_Users",
                         "Avg_Speed_Mbps", "Total_Cluster_Headroom"],
            )
            .properties(height=max(260, 18 * len(frame)))
        )
        st.altair_chart(chart, width="stretch")
        st.dataframe(frame, hide_index=True, width="stretch")

with tower_tab:
    tower = st.text_input("Tower ID", value="TWR_0029", help="Anonymised ERBS ID, e.g. TWR_0001 to TWR_1067")
    result, tower_error = get_json(KPI_API_URL, f"/towers/{tower.strip()}/forecast", timeout=15.0)
    if tower_error:
        st.warning(f"No forecast for {tower}: {tower_error}")
    else:
        names = {
            "connected_users": "Connected users",
            "dl_throughput_mbps": "DL throughput (Mbps)",
            "availability_pct": "Availability (%)",
            "erab_drop_rate": "E-RAB drop rate (%)",
        }
        charts = []
        for key, label in names.items():
            frame = pd.DataFrame(result["series"][key]).melt("date", var_name="series", value_name="value")
            frame["date"] = pd.to_datetime(frame["date"])
            charts.append(
                alt.Chart(frame, title=label)
                .mark_line()
                .encode(
                    x=alt.X("date:T", title=None),
                    y=alt.Y("value:Q", title=None),
                    color=alt.Color("series:N", scale=alt.Scale(domain=["actual", "predicted"],
                                                                range=["#0b1f3a", "#12b3a8"]),
                                    legend=alt.Legend(title=None, orient="top")),
                )
                .properties(height=200)
            )
        top = alt.hconcat(charts[0], charts[1])
        bottom = alt.hconcat(charts[2], charts[3])
        st.altair_chart(alt.vconcat(top, bottom), width="stretch")
        st.caption(
            "Next-day predictions against what happened. Load and speed track well "
            "(site-level R² about 0.9); availability and drop rate much less so (about 0.4). "
            "The congestion score weights load 50%, speed 40% and drop rate 10%, and does "
            "not use availability, so it rests mostly on the two better-predicted KPIs."
        )
