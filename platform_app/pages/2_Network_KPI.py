"""Every network KPI the operator's data holds: live SLA health, per-band forecasts,
their held-out accuracy, and the 4G traffic volume forecast. Read-only."""

import altair as alt
import pandas as pd
import streamlit as st
from _shared import KPI_API_URL, configure, get_json, hero

configure("Network KPI", icon="monitoring")

hero(
    "Network KPIs",
    "All 10 radio KPIs across the 6 carrier bands - live SLA status, per-band "
    "forecasts with their own accuracy flag, and 4G traffic volume.",
    badges=["Accessibility", "Retainability", "Mobility", "Capacity", "Availability"],
)

health, error = get_json(KPI_API_URL, "/health")
if error:
    st.error(f"KPI API is unreachable at {KPI_API_URL}: {error}")
    st.stop()

catalog, catalog_error = get_json(KPI_API_URL, "/kpis/catalog")
if catalog_error:
    st.error(f"KPI catalogue unavailable: {catalog_error}")
    st.stop()

kpis = {k["key"]: k for k in catalog["kpis"]}
bands = {b["band"]: b for b in catalog["bands"]}

health_tab, forecast_tab, scorecard_tab, traffic_tab = st.tabs([
    ":material/health_and_safety: KPI health",
    ":material/query_stats: KPI forecasts",
    ":material/fact_check: Forecast accuracy",
    ":material/data_usage: Traffic volume",
])

# ---------------------------------------------------------------------------
with health_tab:
    status, status_error = get_json(KPI_API_URL, "/kpis/status")
    if status_error:
        st.error(f"KPI status unavailable: {status_error}")
    else:
        rows = pd.DataFrame(status["status"])
        c1, c2, c3 = st.columns(3)
        c1.metric("Latest observed day", status["as_of"])
        c2.metric("KPI readings checked", status["checked"])
        c3.metric("SLA breaches", status["breaches"])

        rows["kpi_name"] = rows["kpi"].map(lambda k: kpis[k]["name"])
        rows["band_label"] = rows["band"].map(lambda b: f"{b} MHz")
        rows["result"] = rows["sla_met"].map({True: "Meets SLA", False: "Breach"}).fillna("No data")

        grid = (
            alt.Chart(rows)
            .mark_rect(stroke="white", strokeWidth=2)
            .encode(
                x=alt.X("band_label:N", title="Band", sort=[f"{b} MHz" for b in bands]),
                y=alt.Y("kpi_name:N", title=None, sort=[kpis[k]["name"] for k in kpis]),
                color=alt.Color(
                    "result:N",
                    scale=alt.Scale(domain=["Meets SLA", "Breach", "No data"],
                                    range=["#12b3a8", "#e0533d", "#c7cfdb"]),
                    legend=alt.Legend(title=None, orient="top"),
                ),
                tooltip=[
                    alt.Tooltip("kpi_name:N", title="KPI"),
                    alt.Tooltip("band_label:N", title="Band"),
                    alt.Tooltip("value:Q", title="Observed", format=",.3f"),
                    alt.Tooltip("result:N", title="SLA"),
                ],
            )
            .properties(height=380)
        )
        st.altair_chart(grid, width="stretch")

        breaches = rows[rows["sla_met"] == False]  # noqa: E712
        if not breaches.empty:
            st.subheader("Breaches to review")
            table = breaches.assign(
                SLA=breaches["kpi"].map(lambda k: kpis[k]["sla_description"]),
            )[["band_label", "kpi_name", "value", "sla_value", "SLA"]]
            st.dataframe(
                table.rename(columns={"band_label": "Band", "kpi_name": "KPI",
                                      "value": "Observed", "sla_value": "Compared to SLA"}),
                hide_index=True, width="stretch",
            )
        st.caption(
            "Straight from the per-band carrier export, no model involved. Cell downtime "
            "is recorded per band cluster, so it is divided by the band's cell count "
            "before comparing to its per-cell SLA."
        )

# ---------------------------------------------------------------------------
with forecast_tab:
    left, middle, right = st.columns([2, 2, 1])
    kpi = left.selectbox("KPI", list(kpis), format_func=lambda k: kpis[k]["name"])
    band = middle.selectbox("Band", list(bands), format_func=lambda b: bands[b]["name"])
    days = right.selectbox("Days ahead", [14, 30, 90, 180, 365], index=1)

    forecast, forecast_error = get_json(
        KPI_API_URL, f"/kpis/forecast/{band}/{kpi}?days={days}&history_days=120", timeout=15.0
    )
    if forecast_error:
        st.info(f"No forecast available: {forecast_error}")
    else:
        meta = kpis[kpi]
        if forecast["beats_naive"]:
            st.success(
                f"Trustworthy forecast: {forecast['model']} beat a naive baseline on held-out "
                f"data (MASE {forecast['test_mase']:.2f}).",
                icon=":material/verified:",
            )
        else:
            st.warning(
                f"Trend sketch only: {forecast['model']} did not beat a naive baseline on "
                f"held-out data (MASE {forecast['test_mase']:.2f}). Treat the line as "
                "direction, not a prediction.",
                icon=":material/warning:",
            )

        m1, m2, m3 = st.columns(3)
        m1.metric("SLA", meta["sla_description"])
        m2.metric("Forecast days breaching SLA", f"{forecast['forecast_breach_days']} / {len(forecast['forecast'])}")
        m3.metric("Held-out R²", f"{forecast['test_r2']:.2f}")

        history = pd.DataFrame(forecast["history"]).assign(series="Observed")
        future = pd.DataFrame(forecast["forecast"]).assign(series="Forecast")
        for frame in (history, future):
            frame["date"] = pd.to_datetime(frame["date"])
        lines = pd.concat([history[["date", "value", "series"]], future[["date", "value", "series"]]])

        ribbon = alt.Chart(future).mark_area(opacity=0.22, color="#1454a3").encode(
            x="date:T", y=alt.Y("p05:Q", title=f"{meta['name']} ({meta['unit']})"), y2="p95:Q"
        )
        line = alt.Chart(lines).mark_line().encode(
            x=alt.X("date:T", title=None),
            y="value:Q",
            color=alt.Color("series:N", scale=alt.Scale(domain=["Observed", "Forecast"],
                                                        range=["#0b1f3a", "#1454a3"]),
                            legend=alt.Legend(title=None, orient="top")),
            strokeDash=alt.condition(alt.datum.series == "Forecast", alt.value([6, 3]), alt.value([1, 0])),
        )
        layers = [ribbon, line]
        if kpi != "downtime_sec":
            layers.append(alt.Chart(pd.DataFrame({"sla": [meta["sla_target"]]}))
                          .mark_rule(color="#e0533d", strokeDash=[4, 4]).encode(y="sla:Q"))
        st.altair_chart(alt.layer(*layers).properties(height=360), width="stretch")
        st.caption(
            "Shaded band: the pipeline's 5th-95th percentile range. Red dashed line: SLA "
            "target. The gap between the last observed day and the first forecast day "
            "comes from the forecast run itself, not from this page."
        )

# ---------------------------------------------------------------------------
with scorecard_tab:
    scorecard, scorecard_error = get_json(KPI_API_URL, "/kpis/scorecard")
    if scorecard_error:
        st.info(f"No forecast accuracy available: {scorecard_error}")
    else:
        frame = pd.DataFrame(scorecard["scorecard"])
        s1, s2 = st.columns(2)
        s1.metric("Band x KPI forecasts", scorecard["series"])
        s2.metric("Beat a naive baseline on held-out data", f"{scorecard['beat_naive']} / {scorecard['series']}")

        frame["kpi_name"] = frame["kpi"].map(lambda k: kpis[k]["name"])
        frame["band_label"] = frame["carrier"].map(lambda b: f"{b} MHz")
        frame["verdict"] = frame["beats_naive"].map({True: "Beats naive", False: "Trend only"})
        chart = (
            alt.Chart(frame)
            .mark_rect(stroke="white", strokeWidth=2)
            .encode(
                x=alt.X("band_label:N", title="Band", sort=[f"{b} MHz" for b in bands]),
                y=alt.Y("kpi_name:N", title=None),
                color=alt.Color("verdict:N", scale=alt.Scale(domain=["Beats naive", "Trend only"],
                                                             range=["#12b3a8", "#f0a63c"]),
                                legend=alt.Legend(title=None, orient="top")),
                tooltip=["kpi_name", "band_label", "best_model",
                         alt.Tooltip("test_mase:Q", format=".2f", title="Test MASE"),
                         alt.Tooltip("test_r2_bench:Q", format=".2f", title="Test R²")],
            )
            .properties(height=380)
        )
        st.altair_chart(chart, width="stretch")
        st.caption(
            "MASE below 1 means the model's held-out error is smaller than a naive "
            "baseline's. Availability, connected users and downtime don't beat it on any "
            "band yet - their forecasts are shown, but labelled as trend sketches."
        )

# ---------------------------------------------------------------------------
with traffic_tab:
    horizon = st.selectbox("Forecast horizon (days)", [7, 14, 30, 60, 90], index=2)
    with st.spinner("Running the traffic pipeline (clean, split, benchmark, retrain, forecast)..."):
        result, traffic_error = get_json(KPI_API_URL, f"/traffic/{horizon}day", timeout=30.0)
    if traffic_error:
        st.error(f"Traffic forecast unavailable: {traffic_error}")
    else:
        st.subheader(f"Champion model: {result['champion_model']}")
        metric_cols = st.columns(len(result["test_metrics"]))
        for column, (name, value) in zip(metric_cols, result["test_metrics"].items()):
            column.metric(name, f"{value:,.2f}")
        st.caption(
            "Held-out metrics from a chronological split. Uses traffic history only: "
            "adding the other KPIs as inputs did not improve held-out accuracy."
        )
        traffic = pd.DataFrame(result["forecast"])
        traffic["date"] = pd.to_datetime(traffic["date"])
        band_area = alt.Chart(traffic).mark_area(opacity=0.22, color="#1454a3").encode(
            x=alt.X("date:T", title=None), y=alt.Y("lower_95:Q", title="GB"), y2="upper_95:Q"
        )
        band_line = alt.Chart(traffic).mark_line(color="#1454a3").encode(x="date:T", y="predicted_kpi_volume_gb:Q")
        st.altair_chart((band_area + band_line).properties(height=340), width="stretch")
