"""Live view over the GIS Antenna Planning API. Read-only; assesses a coordinate on request."""

import pandas as pd
import streamlit as st
from _shared import GIS_API_URL, configure, get_json, hero

configure("GIS Planning", icon="cell_tower")

hero(
    "GIS Antenna Planning",
    "Explainable planning-priority scoring over corrected terrain, population and "
    "road features, from antenna_cell_placement's own API.",
)

health, error = get_json(GIS_API_URL, "/health")
if error:
    st.error(f"GIS API is unreachable at {GIS_API_URL}: {error}")
    st.stop()

if health["status"] != "ok":
    st.warning("Required source data is not verified in this environment; scores below may be unavailable.")
with st.expander("Source verification detail"):
    st.json(health["sources"])

st.divider()
st.subheader("Shortlisted sites - latest completed run")
shortlist, shortlist_error = get_json(GIS_API_URL, "/shortlist")
if shortlist_error:
    st.info(f"No completed planning run to show yet ({shortlist_error}).")
else:
    features = shortlist.get("features", [])
    rows = [feature["properties"] for feature in features]
    table = pd.DataFrame(rows)

    top1, top2, top3 = st.columns(3)
    top1.metric("Shortlisted candidates", len(features))
    if not table.empty and "planning_priority_score" in table:
        top2.metric("Top score", f"{table['planning_priority_score'].max():.1f}")
        top3.metric("Median score", f"{table['planning_priority_score'].median():.1f}")

    if not table.empty and {"canonical_latitude", "canonical_longitude"}.issubset(table.columns):
        st.map(
            table.rename(columns={"canonical_latitude": "latitude", "canonical_longitude": "longitude"}),
            latitude="latitude",
            longitude="longitude",
            size=60,
        )
    st.dataframe(table, width="stretch")

st.divider()
st.subheader("Assess a coordinate")
col1, col2, col3 = st.columns(3)
lat = col1.number_input("Latitude", value=32.8, format="%.6f")
lon = col2.number_input("Longitude", value=13.2, format="%.6f")
operator = col3.selectbox("Operator", ["all", "almadar", "libyana"])

if st.button("Assess"):
    result, assess_error = get_json(GIS_API_URL, f"/assess?lat={lat}&lon={lon}&operator={operator}")
    if assess_error:
        st.error(f"Assessment unavailable: {assess_error}")
    else:
        st.json(result)
