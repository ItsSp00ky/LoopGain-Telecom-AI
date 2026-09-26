"""Screen 2 - one customer: risk, reasons, tier, the Almadar bundle held and the offer."""

import pandas as pd
import streamlit as st
from _shared import configure, degraded_notice, lyd, missing_banner, rtl, state, use_campaign

from prepaid_churn.almadar import InvalidCatalogueError, load_market
from prepaid_churn.bundle import BundleError
from prepaid_churn.demo import (
    CAMPAIGNS_DIR,
    DemoPaths,
    offer_row,
    propose_offers,
    subscriber_view,
    utc_today,
)
from prepaid_churn.privacy import looks_like_phone_number
from prepaid_churn.retention import NO_OFFER, RetentionError

configure("Subscriber", icon="person")
demo = state()

st.title("Subscriber")

if missing_banner(demo, ("portfolio",)):
    st.stop()

portfolio = demo.portfolio

left, random_column, risky_column = st.columns([3, 1, 1])

# The buttons are handled before the box is drawn, and write into the box's own state.
# Keeping a separate "picked" value meant a typed ID silently won over the button, so
# "Pick one at random" looked broken once anything had been typed. Only visible on screen.
with random_column:
    st.write("")
    if st.button("Pick one at random", width="stretch"):
        st.session_state["subscriber_id"] = str(portfolio["subscriber_id"].sample(1).iloc[0])
        st.rerun()

with risky_column:
    st.write("")
    # Most of this base is not at risk, so a random customer is almost always a "no
    # offer". Someone opening this screen to see what an offer looks like was picking
    # one customer after another to find one, which is a bad first minute.
    risky = portfolio.loc[portfolio.get("risk_band", pd.Series(dtype="str")).eq("high")]
    if st.button("Pick a high-risk one", width="stretch", disabled=risky.empty):
        st.session_state["subscriber_id"] = str(risky["subscriber_id"].sample(1).iloc[0])
        st.rerun()

with left:
    subscriber_id = st.text_input(
        "Subscriber ID",
        key="subscriber_id",
        placeholder="a pseudonymous ID, never a phone number",
        help="IDs are pseudonymous by contract. A Libyan mobile number is refused here.",
    ).strip()

if not subscriber_id:
    st.info("Enter an ID, or pick one at random.", icon=":material/search:")
    st.stop()

# The privacy rule is enforced here as well as in the T15 service, because a Streamlit
# widget value reaches the session state and the server log before any lookup happens.
if looks_like_phone_number(subscriber_id):
    st.error(
        "**That looks like a Libyan mobile number.** This module only handles "
        "pseudonymous IDs, so nothing was looked up. An operator hashes numbers with "
        "`prepaid_churn.privacy.pseudonymize` before exporting them.",
        icon=":material/block:",
    )
    st.stop()

subscriber = subscriber_view(demo, subscriber_id)
if subscriber is None:
    st.warning("That ID is not in the current export.", icon=":material/person_off:")
    st.stop()

st.code(subscriber_id, language=None)
degraded_notice(demo)

# --- The headline numbers ----------------------------------------------------
probability = subscriber.get("churn_probability")
has_probability = probability is not None and not pd.isna(probability)

a, b, c, d = st.columns(4)
a.metric(
    "Churn probability",
    "-" if not has_probability else f"{float(probability):.1%}",
    help="Calibrated: 0.30 means about 30 in 100 such customers go silent next month.",
)
b.metric("Risk band", str(subscriber.get("risk_band") or "-"))
c.metric("Value tier", str(subscriber.get("value_tier") or "-"))
d.metric(
    "12-month value",
    lyd(subscriber.get("value_12m_base_lyd"), digits=2),
    help="The base hazard scenario of T10, not a measured lifetime value.",
)

st.divider()

profile_column, reason_column = st.columns([1, 2])

with profile_column:
    st.subheader("In Almadar terms")
    st.markdown(
        f"**Monthly spend** {lyd(subscriber.get('monthly_spend_lyd'), digits=2)}  \n"
        f"**Usual recharge card** {lyd(subscriber.get('usual_card_lyd'), digits=0)}  \n"
        f"**Bundle held** `{subscriber.get('bundle_held') or '-'}`  \n"
        f"**Value score** {subscriber.get('value_score', '-')}"
    )
    st.caption(
        f"Spend is converted at the assumed {load_market()['arpu']['monthly_lyd']:.0f} LYD "
        "monthly ARPU of T18 (decision 42). "
        "The bundle held is inferred from the real monthly and short pack purchases in "
        "the source data, not from an Almadar subscription record."
    )

with reason_column:
    st.subheader("Why the model thinks so")
    reasons = subscriber.get("reasons") or []
    if not reasons:
        st.info(
            "No reasons in this export. They come from a bundle-backed scoring run "
            "(`uv run churn tiers` with a gated bundle).",
            icon=":material/info:",
        )
    else:
        st.caption(
            "Exact SHAP contributions from the model that scored this customer, written "
            "as sentences. Only factors that raise the risk are listed."
        )
        for position, reason in enumerate(reasons, start=1):
            st.markdown(f"{position}. {reason}")

st.divider()

# --- What the engine proposed ------------------------------------------------
st.subheader("Proposed retention offer")

offer_id = subscriber.get("recommended_offer_id")
status = str(subscriber.get("status") or "")

if offer_id is None:
    st.info(
        "This customer is not in the campaign the screens are reading.",
        icon=":material/info:",
    )
    # One customer, the same decision path as a whole campaign: the policy chooses the
    # package and the guardrails still apply. The screen only chooses who is considered,
    # and a named person still has to approve whatever comes out (decision 14).
    st.caption(
        "Propose an offer for this one customer. It runs the same engine as a campaign, "
        "writes its own campaign directory, and approves nothing."
    )
    budget = st.number_input("Budget for this customer (LYD)", min_value=0.0, value=5.0, step=1.0)
    if st.button("Propose an offer for this customer", type="primary"):
        directory = CAMPAIGNS_DIR / f"ui-{subscriber_id}-{utc_today()}"
        try:
            with st.spinner("Scoring this customer and asking the engine..."):
                propose_offers(
                    DemoPaths.from_environment(),
                    directory,
                    subscribers=[subscriber_id],
                    budget_lyd=budget,
                )
        except (
            BundleError,
            InvalidCatalogueError,
            RetentionError,
            FileNotFoundError,
            ValueError,
        ) as error:
            st.error(str(error), icon=":material/error:")
        else:
            use_campaign(directory)
            st.rerun()
elif str(offer_id) == NO_OFFER:
    st.info(
        f"**No offer.** {subscriber.get('offer_reason_en') or 'No reason recorded.'}\n\n"
        "Not spending is a first-class outcome here, and on this base it is the usual one.",
        icon=":material/do_not_disturb_on:",
    )
    if subscriber.get("offer_reason_ar"):
        st.markdown(rtl(subscriber["offer_reason_ar"]), unsafe_allow_html=True)
else:
    offer = offer_row(demo, offer_id)
    badge = {"approved": "success", "rejected": "error"}.get(status, "info")
    getattr(st, badge)(
        f"**{offer_id}** - status `{status or 'proposed'}`"
        + (f", reviewed by {subscriber['reviewer']}" if subscriber.get("reviewer") else ""),
        icon=":material/local_offer:",
    )
    if offer is not None:
        st.metric(offer.get("name_en") or offer_id, lyd(offer.get("price_lyd"), digits=2))
        st.markdown(rtl(str(offer.get("name_ar") or "")), unsafe_allow_html=True)
    st.markdown(f"**Why** {subscriber.get('offer_reason_en') or '-'}")
    st.markdown(rtl(subscriber.get("offer_reason_ar") or ""), unsafe_allow_html=True)

    cost, value = subscriber.get("expected_cost_lyd"), subscriber.get("expected_net_value_lyd")
    one, two = st.columns(2)
    one.metric("Assumed delivery cost", lyd(cost, digits=2))
    two.metric("Assumed net value", lyd(value, digits=2))
    st.caption(
        "Both figures are assumptions from `data/almadar/retention.toml`, not measured "
        "profit or causal uplift. An offer is sent only after a named reviewer approves "
        "it on the campaign screen."
    )
    if status == "approved":
        st.info(
            "This one is approved, so it is on the **Released** screen and the chatbot "
            "can be told about it.",
            icon=":material/verified:",
        )
    elif status != "rejected":
        st.info(
            "Waiting for a review. Approve or reject it on the **Campaign builder** "
            "screen, under your own name.",
            icon=":material/how_to_reg:",
        )
