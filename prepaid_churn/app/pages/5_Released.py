"""Screen 5 - what was approved, where it is kept and who is allowed to read it.

The question this screen exists for is "I approved an offer, where did it go".
The answer has three parts, and all three are on this page: the rows themselves, the
files that hold them, and the one endpoint that serves them to the chatbot.
"""

import streamlit as st
from _shared import campaign_dir, configure, lyd, missing_banner, rtl, state

from prepaid_churn.demo import released_offers

configure("Released", icon="verified")
demo = state()

st.title("Released offers")

if missing_banner(demo, ("campaign",)):
    st.stop()

released = released_offers(demo)
directory = campaign_dir()

st.caption(
    f"Campaign `{demo.campaign['campaign_id'][:12]}` in `{directory.name}`. "
    "Only approved rows are here; pending, rejected and holdout customers never enter it."
)

if released.empty:
    st.info(
        "**Nothing has been approved in this campaign yet.**\n\n"
        "Go to the **Campaign builder** screen, pick the customers you want, put your "
        "name in and approve them. They appear here immediately.",
        icon=":material/inbox:",
    )
    st.stop()

first, second, third = st.columns(3)
first.metric("Approved customers", f"{len(released):,}")
second.metric("Different packages", f"{released['offer_id'].nunique():,}")
third.metric(
    "Catalogue value given away",
    lyd(released["price_lyd"].sum(), digits=2),
    help="The list price of the packages granted as bonuses, not money spent.",
)

st.dataframe(
    released[["subscriber_id", "offer_id", "package", "price_lyd", "reviewer", "reviewed_at"]],
    width="stretch",
    hide_index=True,
)

st.subheader("What the customer would be sent")
chosen = st.selectbox("Customer", released["subscriber_id"].tolist())
row = released.loc[released["subscriber_id"].eq(chosen)].iloc[0]
st.markdown(rtl(str(row["reason_ar"])), unsafe_allow_html=True)
st.caption(
    f"Package {row['offer_id']} ({row['package']}), approved by {row['reviewer']} at "
    f"{row['reviewed_at']}. The **Message preview** screen shows the full message and "
    "what it costs to send."
)

st.divider()
st.subheader("Where this lives")

files = {
    "The authority": (
        "proposals.json",
        "the snapshot every decision is written into",
    ),
    "The readable copy": (
        "released.csv",
        "derived from the snapshot, and never the source of truth",
    ),
    "The audit trail": (
        "review_log.jsonl",
        "one line per decision, with the name and the time",
    ),
}
st.markdown(
    "| What | File | |\n|---|---|---|\n"
    + "\n".join(f"| {what} | `{directory / name}` | {why} |" for what, (name, why) in files.items())
)
st.caption(
    "Editing the CSV approves nothing: the service reads the snapshot, so a hand-edited "
    "row is ignored."
)

st.download_button(
    "Download released.csv",
    data=(directory / "released.csv").read_bytes(),
    file_name=f"released-{directory.name}.csv",
    mime="text/csv",
)

st.subheader("Who is served this")
st.markdown(
    """
    The customer chatbot asks the T15 service for one subscriber at a time, with its own
    API key, and gets an offer only if it is on this page:

    ```bash
    curl -H "X-API-Key: $PREPAID_CHURN_CHATBOT_KEY" \\
      http://127.0.0.1:8000/subscribers/<id>/retention
    ```

    A subscriber with no approved offer returns 404, which is also what a rejected or
    unreviewed one returns: the chatbot cannot tell the difference, so a customer can
    never learn that an offer was considered and refused.

    The service reads the campaign once when it starts, so restart `uv run churn serve`
    after approving to serve what is on this page.
    """
)
