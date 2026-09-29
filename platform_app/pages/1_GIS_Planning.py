"""Live view over the GIS Antenna Planning API. Read-only; assesses a coordinate on request."""

import pandas as pd
import streamlit as st
from _shared import GIS_API_URL, configure, get_json

configure("GIS Planning", icon="cell_tower")

st.title(":material/cell_tower: GIS Antenna Planning")
st.caption(
    "Explainable planning-priority scoring over corrected terrain, population and road "
    "features. Calls `antenna_cell_placement`'s own API - nothing here reimplements it."
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
st.subheader("Existing planning run")
shortlist, shortlist_error = get_json(GIS_API_URL, "/shortlist")
if shortlist_error:
    st.info(f"No completed planning run to show yet ({shortlist_error}).")
else:
    features = shortlist.get("features", [])
    st.write(f"{len(features)} shortlisted sites from the most recent completed run.")
    if features:
        rows = [feature["properties"] for feature in features]
        st.dataframe(pd.DataFrame(rows), width="stretch")

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
