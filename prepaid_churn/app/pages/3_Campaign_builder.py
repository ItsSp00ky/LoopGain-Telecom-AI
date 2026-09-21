"""Screen 3 - the campaign: what the guardrails removed, what it costs, and who approves it.

The approval here is the same operation as `churn approve`: it goes through
`campaign.review_file`, which takes the lock, replaces the authoritative JSON atomically
and records a named audit event (decision 14).
It is the only thing in this app that writes anything.
"""

import pandas as pd
import streamlit as st
from _shared import configure, lyd, missing_banner, ordered_bar, refresh, state

from prepaid_churn.campaign import review_file
from prepaid_churn.demo import (
    budget_preview,
    campaign_totals,
    guardrail_rejections,
    pending_proposals,
)
from prepaid_churn.retention import NO_OFFER, RetentionError

configure("Campaign builder", icon="campaign")
demo = state()

st.title("Campaign builder")

if missing_banner(demo, ("campaign",)):
    st.stop()

decisions = demo.decisions
policy = demo.campaign["snapshot"]["policy"]
totals = campaign_totals(decisions)

st.caption(
    f"Campaign `{demo.campaign['campaign_id'][:12]}`, proposed "
    f"{demo.campaign['snapshot']['created_at']}, policy `{policy['budget_lyd']:,.0f} LYD` "
    f"budget and {policy['holdout_fraction']:.0%} holdout."
)

a, b, c, d = st.columns(4)
a.metric("Customers decided", f"{totals['rows']:,}")
b.metric("Offers proposed", f"{totals['offers']:,}")
c.metric("Assumed cost", lyd(totals.get("expected_cost_lyd"), digits=2))
d.metric("Held out", f"{totals['holdout']:,}", help="A random control arm that gets no offer.")

held = totals["holdout"]
st.info(
    f"**{held:,} customer{'' if held == 1 else 's'} held out, receiving nothing.** "
    "Without a control arm there is no way to measure whether a campaign worked, and "
    "every effectiveness claim becomes an assertion.",
    icon=":material/science:",
)

st.divider()

# --- What the guardrails removed ---------------------------------------------
st.subheader("1. What the guardrails removed")

rejections = guardrail_rejections(decisions)
if rejections.empty:
    st.info("No guardrail removed a customer in this campaign.", icon=":material/info:")
else:
    st.altair_chart(
        ordered_bar(
            rejections,
            rejections["reason"].tolist(),
            label="reason",
            horizontal=True,
            height=40 * len(rejections) + 60,
        ),
        use_container_width=True,
    )
    st.dataframe(rejections, width="stretch", hide_index=True)
    st.caption(
        f"**{int(rejections['customers'].sum()):,} of {totals['rows']:,} removed before any "
        "money was allocated**, each with a stated reason. A campaign tool that cannot say "
        "who it excluded and why is one nobody should sign off."
    )

st.divider()

# --- The equal-spend comparison ----------------------------------------------
st.subheader("2. Against spending the same money untargeted")

comparison = pd.DataFrame(demo.campaign["snapshot"]["comparison"])
if comparison.empty:
    st.info("This campaign recorded no comparison.", icon=":material/info:")
else:
    st.dataframe(comparison, width="stretch", hide_index=True)
    st.caption(
        "Every approach is compared at the **same expected spend**. Comparing a budgeted "
        "campaign against an unconstrained blanket one measures the size of the budget, "
        "not the quality of the targeting."
    )

st.divider()

# --- A different budget, as a preview only -----------------------------------
st.subheader("3. Try a different budget")
st.caption(
    "A preview over this campaign's own stored inputs and catalogue, with only the budget "
    "changed. It runs no model, it is never written, and nothing in it can be approved: "
    "approval always acts on the campaign `churn decide` wrote. "
    "To make a different budget real, run `churn decide --budget` into a new directory."
)

current = float(policy["budget_lyd"])
budget = st.slider(
    "Campaign budget (LYD)",
    0.0,
    max(current * 4, 100.0),
    current,
    step=max(current / 20, 10.0),
)

if st.button("Preview this budget"):
    try:
        preview, preview_comparison = budget_preview(demo.campaign, budget)
    except RetentionError as error:
        st.error(str(error), icon=":material/error:")
    else:
        offered = preview["recommended_offer_id"].astype(str).ne(NO_OFFER)
        count = int(offered.sum())
        one, two, three = st.columns(3)
        one.metric("Offers", f"{count:,}", delta=f"{count - totals['offers']:+,}")
        two.metric("Assumed cost", lyd(preview.loc[offered, "expected_cost_lyd"].sum(), digits=2))
        three.metric(
            "Assumed net value",
            lyd(preview.loc[offered, "expected_net_value_lyd"].sum(), digits=2),
        )
        st.dataframe(preview_comparison, width="stretch", hide_index=True)
        st.caption("Preview only. Nothing above was written or proposed.")

st.divider()

# --- Named approval -----------------------------------------------------------
st.subheader("4. Approve or reject, under your name")

pending = pending_proposals(decisions)
pending_offers = pending.loc[pending["recommended_offer_id"].astype(str).ne(NO_OFFER)]

e, f, g = st.columns(3)
e.metric("Pending offers", f"{len(pending_offers):,}")
f.metric("Approved", f"{totals['approved']:,}")
g.metric("Rejected", f"{totals['rejected']:,}")

if pending_offers.empty:
    st.info(
        "No proposal is waiting for a review. Only rows with an actual offer can be "
        "reviewed; a `NO_OFFER` row has nothing to approve.",
        icon=":material/inbox:",
    )
else:
    columns = [
        name
        for name in (
            "subscriber_id",
            "recommended_offer_id",
            "offer_reason_en",
            "expected_cost_lyd",
            "expected_net_value_lyd",
        )
        if name in pending_offers.columns
    ]
    st.dataframe(pending_offers[columns].head(200), width="stretch", hide_index=True)
    if len(pending_offers) > 200:
        st.caption(f"Showing the first 200 of {len(pending_offers):,}.")

    reviewer = st.text_input("Your name", help="Recorded against every decision you make.")
    chosen = st.multiselect(
        "Subscribers to review",
        pending_offers["subscriber_id"].astype(str).tolist(),
        help="Leave empty to review every pending proposal at once.",
    )
    note = st.text_input("Note (optional)")

    approve, reject = st.columns(2)
    for column, decision, label in (
        (approve, "approved", "Approve"),
        (reject, "rejected", "Reject"),
    ):
        with column:
            if st.button(f"{label} selected", width="stretch", type="primary"):
                if not reviewer.strip():
                    st.error("A reviewer name is required.", icon=":material/error:")
                else:
                    try:
                        review_file(
                            demo.campaign_path,
                            reviewer,
                            decision,
                            chosen or None,
                            note,
                        )
                    except RetentionError as error:
                        st.error(str(error), icon=":material/error:")
                    else:
                        refresh()
                        st.success(
                            f"{len(chosen) or len(pending_offers)} proposal(s) {decision} "
                            f"by {reviewer.strip()}.",
                            icon=":material/check_circle:",
                        )
                        st.rerun()

st.caption(
    "Only approved rows reach `released.csv`, which is what the chatbot reads through the "
    "T15 service. Rejected and unreviewed rows never leave this screen."
)
