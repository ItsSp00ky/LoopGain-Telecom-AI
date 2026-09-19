"""Screen 2 -- Segment Explorer.  Owner: E5 (data from E3)

RFM-LE heatmap, the dendrogram from hierarchical clustering, a PCA scatter of
the K-Means clusters, and per-segment behaviour cards.

Show where the rule-based segments and the clusters DISAGREE. That disagreement
is the insight, not a defect to reconcile away.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _shared import base, missing_banner, report, synthetic_notice
from cvm.config import settings

st.title("Segment Explorer")

if missing_banner(
    {
        "feature store": settings.feature_store_offline,
        "M2 segmentation": settings.reports_dir / "m2_segmentation.json",
    }
):
    st.stop()

frame = base()
result = report("m2_segmentation.json") or {}

# --- The uncomfortable finding, first ---------------------------------------
st.subheader("Are the eight segments a shape in the data?")

natural = result.get("natural_clusters_from_dendrogram")
declared = result.get("declared_business_segments", frame["segment"].nunique())
chosen_k = result.get("k_chosen")

one, two, three, four = st.columns(4)
one.metric("k by silhouette", chosen_k, help="Chosen by a number, not by eye.")
two.metric("Dendrogram's natural cut", natural, help="The largest merge gap in Ward linkage.")
three.metric("Business segments declared", declared)
four.metric(
    "Adjusted Rand (matched k)",
    f"{result.get('matched_k_adjusted_rand', 0):.3f}",
    help=(
        "Agreement between the rules and the clusters at the SAME k. Comparing "
        "3 clusters with 8 segments is bounded by arithmetic rather than by "
        "disagreement, so only the matched figure is evidence."
    ),
)

if natural and natural != declared:
    st.warning(
        f"**Two independent methods say {natural} groups; the taxonomy says {declared}.** "
        f"Silhouette picks k={chosen_k} and the dendrogram's largest merge gap is at "
        f"{natural}. Adjusted Rand between the rules and the clusters is "
        f"{result.get('matched_k_adjusted_rand', 0):.3f} even after forcing k to "
        f"{declared} — the two labellings are close to independent.\n\n"
        "So the eight RFM-LE segments are a **reporting convention, not a discovered "
        'structure**. They stay useful — "At-Risk Valuable" is legible to a marketing '
        'analyst in a way "cluster 2" is not — but they should be presented as a '
        "chosen vocabulary rather than something the data produced.",
        icon=":material/warning:",
    )
else:
    st.success(
        "The dendrogram's natural cut matches the declared segments.", icon=":material/check:"
    )

synthetic_notice()
st.divider()

# --- Where they disagree, per segment ---------------------------------------
st.subheader("Where the rules and the clusters disagree")

crosstab_path = settings.reports_dir / "m2_rules_vs_clusters_matched_k.csv"
if crosstab_path.exists():
    crosstab = pd.read_csv(crosstab_path, index_col=0)
    share = crosstab.div(crosstab.sum(axis=1), axis=0)
    st.plotly_chart(
        px.imshow(
            share,
            labels={"x": "Rule segment", "y": "Cluster", "color": "Share of cluster"},
            color_continuous_scale="Blues",
            aspect="auto",
            text_auto=".0%",
        ).update_layout(height=420, margin={"t": 20}),
        width="stretch",
    )
    purity = crosstab.max(axis=1) / crosstab.sum(axis=1)
    worst = purity.idxmin()
    st.caption(
        f"A row that is one dark cell is a cluster the rules already have a word for. "
        f"**Cluster {worst} is the least pure at {purity.min():.1%}** — the rules have no "
        "single name for the group the data actually found, which is the most "
        "interesting cell on this screen."
    )
else:
    st.info("Run `python -m cvm.models.m2_value.run` to produce the cross-tab.")

st.divider()

# --- RFM-LE heatmap ---------------------------------------------------------
st.subheader("RFM-LE")

left, right = st.columns([2, 1])
with left:
    dimensions = ["R", "F", "M", "L", "E"]
    pivot = (
        frame.groupby(["R", "F"])["subscriber_id_hashed"]
        .size()
        .reset_index(name="subscribers")
        .pivot(index="R", columns="F", values="subscribers")
        .fillna(0)
    )
    st.plotly_chart(
        px.imshow(
            pivot,
            labels={"x": "Frequency", "y": "Recency", "color": "Subscribers"},
            color_continuous_scale="Viridis",
            aspect="auto",
            text_auto=True,
        ).update_layout(height=380, margin={"t": 20}),
        width="stretch",
    )
    st.caption(
        "Recency is INVERTED: R=5 means recent. Fewer days since a revenue event is "
        "better, so getting this backwards would flip every segment while leaving "
        "the chart looking entirely plausible."
    )

with right:
    means = frame[dimensions].mean().reset_index()
    means.columns = ["dimension", "mean"]
    st.plotly_chart(
        px.line_polar(means, r="mean", theta="dimension", line_close=True, range_r=[0, 5])
        .update_traces(fill="toself")
        .update_layout(height=380, margin={"t": 20}, title="Population mean"),
        width="stretch",
    )

# --- PCA --------------------------------------------------------------------
st.subheader("How many dimensions does RFM-LE really have?")

explained = result.get("pca_explained_variance")
loadings_path = settings.reports_dir / "m2_pca_loadings.csv"
if explained is not None and loadings_path.exists():
    st.metric("Variance in 2 components", f"{explained:.1%}")
    loadings = pd.read_csv(loadings_path, index_col=0)
    st.plotly_chart(
        px.imshow(
            loadings,
            labels={"x": "Component", "y": "Dimension", "color": "Loading"},
            color_continuous_scale="RdBu",
            color_continuous_midpoint=0,
            text_auto=".2f",
            aspect="auto",
        ).update_layout(height=280, margin={"t": 20}),
        width="stretch",
    )
    st.caption(
        f"{explained:.1%} in two components means the five dimensions carry genuinely "
        "different information — RFM-LE is not five names for two things. The "
        "taxonomy above is redundant; the underlying measurements are not."
        if explained < 0.8
        else f"{explained:.1%} in two components: most of RFM-LE collapses into two, so "
        "some of the five dimensions are measuring the same thing."
    )

# --- Per-segment cards ------------------------------------------------------
st.divider()
st.subheader("Segment behaviour")

summary = (
    frame.groupby("segment")
    .agg(
        subscribers=("subscriber_id_hashed", "size"),
        mean_churn=("churn_probability", "mean"),
        median_clv=("clv_12m", "median"),
        mean_recency_days=("days_since_last_topup", "mean"),
        mean_leakage=("leakage_score", "mean"),
    )
    .reset_index()
    .sort_values("mean_churn", ascending=False)
)
st.dataframe(
    summary.style.format(
        {
            "subscribers": "{:,.0f}",
            "mean_churn": "{:.4f}",
            "median_clv": "{:,.0f}",
            "mean_recency_days": "{:.1f}",
            "mean_leakage": "{:.3f}",
        }
    ).background_gradient(subset=["mean_churn"], cmap="Reds"),
    width="stretch",
    hide_index=True,
)
