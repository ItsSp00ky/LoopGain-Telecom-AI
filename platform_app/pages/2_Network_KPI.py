"""Live view over the Network KPI forecast API. Read-only; runs the real pipeline via the API."""

import pandas as pd
import streamlit as st
from _shared import KPI_API_URL, configure, get_json, hero

configure("Network KPI", icon="monitoring")

hero(
    "Network KPI Forecast",
    "4G macro traffic volume forecast: clean -> chronological split -> multi-model "
    "benchmark -> champion retrain -> forecast, from network_kpi_prediction's own API.",
)

health, error = get_json(KPI_API_URL, "/health")
if error:
    st.error(f"KPI API is unreachable at {KPI_API_URL}: {error}")
    st.stop()
if health["status"] != "ok":
    st.warning(f"Raw traffic data not found at {health.get('raw_data_path')}.")
    st.stop()

horizon = st.selectbox("Forecast horizon (days)", [7, 14, 30, 60, 90], index=2)

with st.spinner("Running the real pipeline (clean, split, benchmark, retrain, forecast)..."):
    result, forecast_error = get_json(KPI_API_URL, f"/traffic/{horizon}day", timeout=30.0)

if forecast_error:
    st.error(f"Forecast unavailable: {forecast_error}")
    st.stop()

st.subheader(f"Champion model: {result['champion_model']}")
metric_cols = st.columns(len(result["test_metrics"]))
for column, (name, value) in zip(metric_cols, result["test_metrics"].items()):
    column.metric(name, f"{value:,.2f}")
st.caption("Held-out test metrics from a chronological train/val/test split, not a random split.")

forecast = pd.DataFrame(result["forecast"])
forecast["date"] = pd.to_datetime(forecast["date"])
st.line_chart(forecast.set_index("date")[["predicted_kpi_volume_gb", "lower_95", "upper_95"]])
st.dataframe(forecast, width="stretch")
