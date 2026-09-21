"""Screen 4 - the Arabic message an approved customer would actually receive.

The point of this screen is the part count. One Arabic character forces the whole SMS
into UCS-2, where a part is 70 characters rather than 160, so a message that looks short
can send as three parts and be billed three times.
"""

import pandas as pd
import streamlit as st
from _shared import configure, lyd, missing_banner, rtl, state

from prepaid_churn.demo import customer_message, offer_row, sms_parts, subscriber_view

configure("Message preview", icon="sms")
demo = state()

st.title("Customer message preview")

if missing_banner(demo, ("campaign",)):
    st.stop()

approved = demo.service.approved
if approved.empty:
    st.info(
        "No offer has been approved yet, so there is no message to send. "
        "Approve one on the campaign screen first; this preview deliberately shows only "
        "what a reviewer signed off.",
        icon=":material/inbox:",
    )
    st.stop()

subscriber_id = st.selectbox(
    "Approved customer",
    approved["subscriber_id"].astype(str).tolist(),
    help="Only approved offers appear here.",
)
language = st.radio(
    "Language",
    ["ar", "en"],
    horizontal=True,
    format_func={"ar": "العربية", "en": "English"}.get,
)

subscriber = subscriber_view(demo, subscriber_id) or {}
offer = offer_row(demo, subscriber.get("recommended_offer_id"))
message = customer_message(subscriber, offer, language)

handset, facts = st.columns([2, 1])

with handset:
    st.subheader("As the customer sees it")
    if language == "ar":
        st.markdown(rtl(message), unsafe_allow_html=True)
    else:
        st.markdown(message)
    st.text_area("Plain text", message, height=120, disabled=True)

with facts:
    st.subheader("How it sends")
    parts = sms_parts(message)
    st.metric("Parts", parts["parts"])
    st.metric("Encoding", parts["encoding"])
    st.metric("Characters", f"{parts['length']} of {parts['limit']}")
    if parts["over_one_part"]:
        st.warning(
            f"**This sends as {parts['parts']} SMS parts and is billed as "
            f"{parts['parts']}.** Shorten it to {parts['limit']} characters to send one.",
            icon=":material/warning:",
        )
    else:
        st.success(
            f"One part, {parts['remaining']} characters to spare.",
            icon=":material/check_circle:",
        )
    st.caption(
        "A single Arabic character forces the whole message into UCS-2, where one part "
        "is 70 characters instead of 160. A preview that showed 160 would promise a "
        "one-part message that sends as three."
    )

st.divider()

if offer is not None:
    st.subheader("The package being given")
    left, right = st.columns(2)
    left.markdown(
        f"**{offer.get('name_en') or offer.get('offer_id')}**  \n"
        f"{offer.get('family_en') or '-'}  \n"
        f"Price {lyd(offer.get('price_lyd'), digits=2)}"
    )
    arabic = f"<b>{offer.get('name_ar') or ''}</b><br>{offer.get('family_ar') or ''}"
    with right:
        st.markdown(rtl(arabic), unsafe_allow_html=True)

    # Only one package in the catalogue has a daily window: the 1 LYD morning pass.
    opens, closes = offer.get("valid_from_hour"), offer.get("valid_to_hour")
    if not pd.isna(opens) and not pd.isna(closes):
        st.info(
            f"This package works only between {int(float(opens)):02d}:00 and "
            f"{int(float(closes)):02d}:00, and the message says so.",
            icon=":material/schedule:",
        )

st.caption(
    "The message states the package and the reason the reviewer approved, and nothing "
    "else. No churn probability, risk band or value figure is ever sent to a customer."
)
