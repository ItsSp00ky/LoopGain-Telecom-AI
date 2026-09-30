"""Live view over the GIS Antenna Planning API. Read-only; assesses a coordinate on request."""

import pandas as pd
import pydeck as pdk
import streamlit as st
from _shared import GIS_API_URL, configure, get_json, hero

configure("Site Planning", icon="cell_tower")

hero(
    "Site Planning (GIS)",
    "Where to build the next cell sites: an explainable priority score over population "
    "demand, distance to existing sites, road access and terrain - every rank comes with "
    "its reasons.",
    badges=["Explainable score", "Reconciled antenna inventory", "Engineering review"],
)

health, error = get_json(GIS_API_URL, "/health")
if error:
    st.error(f"GIS API is unreachable at {GIS_API_URL}: {error}")
    st.stop()

shortlist, shortlist_error = get_json(GIS_API_URL, "/shortlist")
if shortlist_error:
    st.info(f"No completed planning run to show yet ({shortlist_error}).")
    st.stop()

table = pd.DataFrame([f["properties"] for f in shortlist.get("features", [])])
if table.empty:
    st.info("The latest planning run has no shortlisted sites.")
    st.stop()

table = table.sort_values("recommendation_rank")
table["reasons"] = table["reason_codes"].fillna("").map(
    lambda codes: " · ".join(c.replace("_", " ").capitalize() for c in codes.split(";") if c)
)
table["nearest_site_km"] = table["dist_to_nearest_site_m"] / 1000
table["people_5km"] = table["population_sum_5km"].round().astype("Int64")

m1, m2, m3, m4 = st.columns(4)
with m1.container(border=True):
    st.metric("Shortlisted sites", len(table))
with m2.container(border=True):
    st.metric("Top priority score", f"{table['planning_priority_score'].max():.1f}")
with m3.container(border=True):
    st.metric("People within 5 km (median)", f"{table['population_sum_5km'].median():,.0f}")
with m4.container(border=True):
    st.metric("Gap to nearest site (median)", f"{table['nearest_site_km'].median():.1f} km")

# Deeper blue = higher priority; labelled with the rank so map and table line up.
low, high = table["planning_priority_score"].min(), table["planning_priority_score"].max()
span = (high - low) or 1.0


def colour(score):
    t = (score - low) / span
    start, end = (142, 197, 255), (11, 61, 145)
    return [round(a + (b - a) * t) for a, b in zip(start, end)] + [235]


table["fill"] = table["planning_priority_score"].map(colour)
table["rank_label"] = table["recommendation_rank"].astype(int).astype(str)
table["score_label"] = table["planning_priority_score"].round(1)

st.subheader("Shortlisted sites")
st.pydeck_chart(
    pdk.Deck(
        map_style=pdk.map_styles.CARTO_LIGHT,
        initial_view_state=pdk.ViewState(
            latitude=table["canonical_latitude"].mean(),
            longitude=table["canonical_longitude"].mean(),
            zoom=9.2,
        ),
        layers=[
            pdk.Layer(
                "ScatterplotLayer",
                data=table,
                get_position=["canonical_longitude", "canonical_latitude"],
                get_fill_color="fill",
                get_line_color=[255, 255, 255],
                get_radius=700,
                radius_min_pixels=9,
                radius_max_pixels=16,
                line_width_min_pixels=1.5,
                stroked=True,
                pickable=True,
            ),
            pdk.Layer(
                "TextLayer",
                data=table,
                get_position=["canonical_longitude", "canonical_latitude"],
                get_text="rank_label",
                get_size=11,
                get_color=[255, 255, 255],
                get_alignment_baseline="'center'",
            ),
        ],
        tooltip={
            "html": "<b>#{rank_label} · {municipality_name}</b><br/>Priority score {score_label}"
                    "<br/>{reasons}",
            "style": {"backgroundColor": "#0b1f3a", "color": "white", "fontSize": "12px"},
        },
    ),
    height=460,
)
st.caption("Darker = higher priority. Numbers are the rank; hover a site for its score and reasons.")

st.dataframe(
    table[[
        "recommendation_rank", "municipality_name", "planning_priority_score", "reasons",
        "people_5km", "nearest_site_km", "dist_to_nearest_road_m", "candidate_status",
    ]],
    column_config={
        "recommendation_rank": st.column_config.NumberColumn("Rank", format="%d", width="small"),
        "municipality_name": "Area",
        "planning_priority_score": st.column_config.ProgressColumn(
            "Priority score", min_value=0, max_value=100, format="%.1f"),
        "reasons": st.column_config.TextColumn("Why it ranks here", width="medium"),
        "people_5km": st.column_config.NumberColumn("People within 5 km", format="localized"),
        "nearest_site_km": st.column_config.NumberColumn("Nearest existing site", format="%.1f km"),
        "dist_to_nearest_road_m": st.column_config.NumberColumn("Nearest road", format="%d m"),
        "candidate_status": st.column_config.TextColumn("Status"),
    },
    hide_index=True,
    width="stretch",
)
with st.expander("All planning features for these sites"):
    st.dataframe(table.drop(columns=["fill", "rank_label", "score_label", "people_5km"]), hide_index=True, width="stretch")

# ---------------------------------------------------------------------------
st.subheader("Assess a coordinate")
st.caption("Scores any point with the same features and rules as the batch run.")
if health["status"] != "ok":
    st.warning(
        "Point assessment needs the planning source data (cleaned inventory, elevation, "
        "land cover, OSM) on this machine, and it isn't all present here, so assessment "
        "will return unavailable. The shortlist above comes from a completed run and is "
        "not affected.",
        icon=":material/info:",
    )
    with st.expander("Which source files are missing or changed"):
        missing = [s for s in health["sources"]["sources"] if s["status"] != "verified"]
        st.dataframe(pd.DataFrame(missing)[["path", "status", "required"]], hide_index=True, width="stretch")

with st.form("assess"):
    col1, col2, col3 = st.columns(3)
    lat = col1.number_input("Latitude", value=32.8, format="%.6f")
    lon = col2.number_input("Longitude", value=13.2, format="%.6f")
    operator = col3.selectbox("Operator", ["all", "almadar", "libyana"])
    submitted = st.form_submit_button("Assess this point", type="primary")

if submitted:
    result, assess_error = get_json(GIS_API_URL, f"/assess?lat={lat}&lon={lon}&operator={operator}", timeout=60.0)
    if assess_error:
        st.error(f"Assessment unavailable: {assess_error}")
    else:
        r1, r2, r3 = st.columns(3)
        r1.metric("Priority score", f"{result.get('planning_priority_score') or 0:.1f}")
        r2.metric("Eligible", "Yes" if result.get("eligible") else "No")
        r3.metric("Nearest existing site", f"{(result.get('dist_to_nearest_site_m') or 0) / 1000:.1f} km")
        if result.get("rejection_reasons"):
            st.warning(f"Not eligible: {result['rejection_reasons'].replace(';', ', ')}")
        with st.expander("Full assessment"):
            st.json(result)
