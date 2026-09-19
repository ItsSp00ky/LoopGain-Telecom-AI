"""Subscriber Channel Simulator.  Owner: E5

A mock of the channels a Libyan prepaid customer actually uses: a USSD menu
flow including a *61121#-style advance option, and an SMS preview, in Arabic
RTL with an English toggle.

Entering a test subscriber shows the exact offer, price and advance limit the
engine selected, with the message copy GROUNDED in the engine's reason codes --
the wording is templated from what the decision returned, never invented.

Low engineering cost, disproportionate demo impact: it collapses the distance
between "we built a model" and "here is what the customer receives".

Run:  streamlit run apps/channel_sim/Home.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _shared import base, missing_banner, rtl, shaped, sms_parts
from cvm.api.schemas import AdvanceLimitRequest, AdvanceProduct, OfferRequest
from cvm.config import settings
from cvm.decision.advance_limit import decide_limit
from cvm.decision.pricing import NO_ACTION, decide_offer

st.set_page_config(page_title="Channel Simulator", page_icon="mobile_phone", layout="centered")

st.title("Subscriber Channel Simulator")
st.caption("What the customer actually receives, from the decision the engine actually made.")

if missing_banner({"feature store": settings.feature_store_offline}):
    st.stop()

frame = base()
language = st.radio("Language", ["العربية", "English"], horizontal=True)
arabic = language == "العربية"

left, right = st.columns([3, 1])
with left:
    subscriber_id = st.text_input("Subscriber ID (hashed)", placeholder="64 hex characters").strip()
with right:
    st.write("")
    if st.button("Random", width="stretch"):
        st.session_state["sim_id"] = str(frame["subscriber_id_hashed"].sample(1).iloc[0])
        st.rerun()

subscriber_id = subscriber_id or st.session_state.get("sim_id", "")
if not subscriber_id:
    st.info("Pick a subscriber to see what the engine would send them.")
    st.stop()

row = frame[frame["subscriber_id_hashed"].astype(str) == subscriber_id]
if row.empty:
    st.warning("Not in the feature store.", icon=":material/person_off:")
    st.stop()

features = row.iloc[0].to_dict()
offer = decide_offer(OfferRequest(subscriber_id=subscriber_id), features)
airtime = decide_limit(
    AdvanceLimitRequest(subscriber_id=subscriber_id, product=AdvanceProduct.AIRTIME), features
)
data_advance = decide_limit(
    AdvanceLimitRequest(subscriber_id=subscriber_id, product=AdvanceProduct.DATA), features
)

tab_ussd, tab_sms = st.tabs(["USSD  *61121#", "SMS"])

# --- USSD -------------------------------------------------------------------
with tab_ussd:
    st.caption(
        "A USSD session is plain text on a feature phone: no images, no styling, "
        "182 characters per screen. Anything that does not fit is a second screen "
        "the subscriber has to ask for."
    )

    if arabic:
        lines = ["المدار الجديد", "", "1. رصيدك"]
        if offer.offer_id != NO_ACTION:
            lines.append(f"2. عرض خاص: {offer.bundle.name_ar or offer.offer_id}")
        if airtime.approved:
            lines.append(f"3. رصيد في وقته ({airtime.limit_lyd:.0f} د.ل)")
        else:
            lines.append("3. رصيد في وقته (غير متاح)")
        lines += ["", "0. خروج"]
    else:
        lines = ["Almadar Aljadid", "", "1. Balance"]
        if offer.offer_id != NO_ACTION:
            lines.append(f"2. Offer: {offer.bundle.name_en or offer.offer_id}")
        lines.append(
            f"3. Emergency credit ({airtime.limit_lyd:.0f} LYD)"
            if airtime.approved
            else "3. Emergency credit (unavailable)"
        )
        lines += ["", "0. Exit"]

    menu = "\n".join(lines)
    st.code(shaped(menu) if arabic else menu, language=None)

    over = len(menu) > 182
    st.caption(
        f"{len(menu)} characters "
        + (":red[over the 182-character USSD screen limit]" if over else "of 182")
    )

    st.divider()
    st.markdown("**What option 3 does**")
    if airtime.approved:
        st.success(
            f"Grants {airtime.limit_lyd:.0f} LYD, bound by `{airtime.binding_constraint}`.",
            icon=":material/check_circle:",
        )
    else:
        st.error(f"Declines, bound by `{airtime.binding_constraint}`.", icon=":material/block:")
        st.markdown(rtl(airtime.customer_facing_reason_ar), unsafe_allow_html=True)

    if not data_advance.approved and data_advance.fallback_offer_id:
        st.warning(
            f"The **data** advance is declined for this subscriber and "
            f"`{data_advance.fallback_offer_id}` is offered instead — declining with "
            "something they can afford rather than declining with nothing.",
            icon=":material/swap_horiz:",
        )

# --- SMS --------------------------------------------------------------------
with tab_sms:
    if offer.offer_id == NO_ACTION:
        st.info(
            "**The engine made no offer, so the simulator sends nothing.** Not spending "
            "is a first-class outcome, and a channel mock that invents a message here "
            "would be showing something the system did not decide.",
            icon=":material/do_not_disturb_on:",
        )
        st.stop()

    # GROUNDED IN THE DECISION. Every number in this message comes from the
    # response object above. The template chooses wording; it never chooses a
    # price, a bonus or a limit.
    if arabic:
        body = offer.customer_facing_reason_ar
        if offer.bonus_mb:
            body += f" {offer.bonus_mb:,} ميجابايت."
        elif offer.discount_pct:
            body += f" السعر {offer.price_lyd:.2f} د.ل."
    else:
        body = offer.customer_facing_reason_en
        if offer.bonus_mb:
            body += f" {offer.bonus_mb:,} MB."
        elif offer.discount_pct:
            body += f" Now {offer.price_lyd:.2f} LYD."

    message = st.text_area("Message", value=body, height=120)

    st.markdown("**Handset preview**")
    st.code(shaped(message) if arabic else message, language=None)

    # THE REAL LIMIT IS 70, NOT 160. One Arabic character forces the whole
    # message into UCS-2, where a single part is 70 characters rather than 160.
    # A preview showing 160 would tell a campaign manager a message fits in one
    # SMS when it will send as three -- and they are billed per part.
    info = sms_parts(message)
    a, b, c = st.columns(3)
    a.metric("Encoding", info["encoding"])
    b.metric("Characters", f"{info['length']} / {info['limit']}")
    c.metric("SMS parts", info["parts"], help="Billing is per part, not per message.")

    if info["encoding"] == "UCS-2":
        st.caption(
            ":material/info: Arabic forces **UCS-2**, so one part is **70 characters, not "
            "160** — and 67 once a message spans parts, because the concatenation header "
            "costs 6 bytes. A single Arabic character in an otherwise Latin message costs "
            "90 characters of capacity."
        )
    if info["over_one_part"]:
        st.warning(
            f"This sends as **{info['parts']} SMS** and is billed as {info['parts']}. "
            f"Trim {abs(info['remaining']) if info['remaining'] < 0 else 0} characters to "
            "fit one part.",
            icon=":material/warning:",
        )
    else:
        st.success(
            f"Fits in one part, {info['remaining']} characters spare.", icon=":material/check:"
        )

    with st.expander("What grounds this message"):
        st.dataframe(
            pd.DataFrame({"reason_code": offer.reason_codes}),
            width="stretch",
            hide_index=True,
        )
        st.caption(
            f"Offer `{offer.offer_id}` at {offer.price_lyd:.2f} LYD via `{offer.instrument}`, "
            f"decision log `{offer.decision_log_id}`. The copy is templated from these; "
            "nothing in the message is generated free-hand, and no model writes a number."
        )
