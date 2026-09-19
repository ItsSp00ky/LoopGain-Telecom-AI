"""Screen 3 -- Subscriber 360.  Owner: E5

The demo centrepiece: 0:45-1:35 of the three-minute pitch runs through this
screen. One hashed ID gives churn probability from BOTH benchmark arms, the
survival curve, RFM-LE scores, CLV, a SHAP waterfall in plain language, the
recommended offer with its computed price, the advance limit WITH ITS REASON,
and the retention stage.

Lookup is by hashed ID only. There is no field on this page that accepts a
raw MSISDN.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _shared import base, missing_banner, rtl, synthetic_notice
from cvm.config import settings

st.title("Subscriber 360")

if missing_banner({"feature store": settings.feature_store_offline}):
    st.stop()

frame = base()

# THE PRIVACY INVARIANT, ENFORCED IN THE UI AND NOT ONLY IN THE BACKEND. This
# field accepts 64 hex characters and nothing else. A raw MSISDN pasted here is
# rejected before it reaches any log, which matters because a Streamlit widget
# value ends up in the session state and the server logs.
MSISDN_HINT = ("+218", "0091", "091", "092", "094", "095", "218")

left, right = st.columns([3, 1])
with left:
    subscriber_id = st.text_input(
        "Subscriber ID (salted SHA-256 hash)",
        placeholder="64 hex characters",
        help="No raw MSISDN is accepted anywhere in this system.",
    ).strip()
with right:
    st.write("")
    if st.button("Pick one at random", width="stretch"):
        st.session_state["random_id"] = str(frame["subscriber_id_hashed"].sample(1).iloc[0])
        st.rerun()

subscriber_id = subscriber_id or st.session_state.get("random_id", "")

if not subscriber_id:
    st.info("Enter a hashed ID, or pick one at random.", icon=":material/search:")
    st.stop()

if any(subscriber_id.startswith(prefix) for prefix in MSISDN_HINT) or subscriber_id.isdigit():
    st.error(
        "**That looks like a phone number.** This system never accepts a raw MSISDN — "
        "identifiers are salted SHA-256 hashes, applied at ingestion. Nothing was "
        "logged or looked up.",
        icon=":material/block:",
    )
    st.stop()

if len(subscriber_id) != 64 or not all(c in "0123456789abcdef" for c in subscriber_id.lower()):
    st.error("A subscriber ID is exactly 64 hexadecimal characters.", icon=":material/error:")
    st.stop()

row = frame[frame["subscriber_id_hashed"].astype(str) == subscriber_id]
if row.empty:
    st.warning("Not in the feature store.", icon=":material/person_off:")
    st.stop()
row = row.iloc[0]


def number(name: str, default: float = 0.0) -> float:
    value = row.get(name, default)
    return default if pd.isna(value) else float(value)


st.code(subscriber_id, language=None)
synthetic_notice()

# --- The four headline numbers ----------------------------------------------
a, b, c, d = st.columns(4)
a.metric(
    "Churn probability (30d)",
    f"{number('churn_probability'):.1%}",
    help="Calibrated: a 0.31 means 31%. The pricing engine multiplies it by money.",
)
b.metric("Risk decile", f"{int(number('risk_decile', 10))}", help="1 is the highest risk.")
c.metric("12-month CLV", f"{number('clv_12m'):,.0f} LYD")
d.metric(
    "Retention ceiling",
    f"{number('retention_ceiling_lyd'):,.2f} LYD",
    help="15% of CLV -- the most the pricing engine may spend on this subscriber.",
)

st.divider()

# --- Who they are -----------------------------------------------------------
profile, drivers = st.columns([1, 2])

with profile:
    st.subheader("Profile")
    st.markdown(
        f"**Segment** {row.get('segment', '—')}  \n"
        f"**Tier** {row.get('tier', '—')}  \n"
        f"**Tenure** {number('tenure_months'):.0f} months  \n"
        f"**RFM-LE cell** `{row.get('rfmle_cell', '—')}`"
    )

    dimensions = ["R", "F", "M", "L", "E"]
    names = ["Recency", "Frequency", "Monetary", "Loyalty", "Engagement"]
    figure = go.Figure(
        go.Scatterpolar(
            r=[number(dim, 3) for dim in dimensions] + [number("R", 3)],
            theta=[*names, names[0]],
            fill="toself",
        )
    )
    figure.update_layout(
        polar={"radialaxis": {"range": [0, 5], "tickvals": [1, 2, 3, 4, 5]}},
        height=300,
        margin={"t": 20, "b": 20},
        showlegend=False,
    )
    st.plotly_chart(figure, width="stretch")

    quadrant = row.get("quadrant")
    if isinstance(quadrant, str):
        colour = {"persuadable": "green", "sleeping_dog": "red"}.get(quadrant, "gray")
        st.markdown(f"**Uplift quadrant** :{colour}[{quadrant}]")
        if quadrant == "sleeping_dog":
            st.error(
                "**Sleeping dog.** Contacting this subscriber makes them MORE likely to "
                "leave. They are excluded from every retention ladder stage.",
                icon=":material/do_not_disturb:",
            )

with drivers:
    st.subheader("Why the model thinks so")
    st.caption(
        "Exact SHAP over the model that actually scored them, rendered as sentences. "
        'Not "days_since_last_topup = 23, shap = +0.14".'
    )

    try:
        import joblib

        from cvm.models.m1_churn.explain import drivers_for_batch, explainer_for
        from cvm.models.m1_churn.gradient_boosting import prepare_matrix

        bundle = joblib.load(settings.models_dir / "m1_churn.joblib")
        matrix, _ = prepare_matrix(row.to_frame().T, columns=bundle["columns"])
        explainer = explainer_for(bundle["model"], matrix)
        top = drivers_for_batch(explainer, matrix, k=6)[0]

        waterfall = pd.DataFrame(top)
        figure = go.Figure(
            go.Bar(
                x=waterfall["contribution"],
                y=waterfall["explanation"],
                orientation="h",
                marker_color=["#c0392b" if v > 0 else "#27ae60" for v in waterfall["contribution"]],
            )
        )
        figure.update_layout(
            height=320,
            margin={"t": 10, "l": 10},
            xaxis_title="Contribution to churn risk",
            yaxis={"autorange": "reversed"},
        )
        st.plotly_chart(figure, width="stretch")

        st.dataframe(
            waterfall[["explanation", "family", "contribution"]].rename(
                columns={"explanation": "Reason", "family": "Family", "contribution": "SHAP"}
            ),
            width="stretch",
            hide_index=True,
        )
    except Exception as exc:  # the screen must still render the rest
        st.warning(f"Explanations unavailable: {exc}", icon=":material/warning:")

st.divider()

# --- What the engine would do -----------------------------------------------
offer_column, advance_column = st.columns(2)

features = row.to_dict()
features["tier"] = row.get("tier", "bronze")

with offer_column:
    st.subheader("Recommended offer")
    try:
        from cvm.api.schemas import OfferRequest
        from cvm.decision.pricing import NO_ACTION, decide_offer

        offer = decide_offer(OfferRequest(subscriber_id=subscriber_id), features)
        if offer.offer_id == NO_ACTION:
            st.info(
                f"**No offer.** {offer.reason_codes[0].split(':', 1)[-1].replace('_', ' ')}.\n\n"
                "Not spending is a first-class outcome here, and usually the right one.",
                icon=":material/do_not_disturb_on:",
            )
        else:
            st.metric(
                offer.bundle.name_en or offer.offer_id,
                f"{offer.price_lyd:,.2f} LYD",
                delta=f"-{offer.discount_pct:.0%}" if offer.discount_pct else "no price cut",
                delta_color="off",
            )
            st.markdown(
                f"**Instrument** `{offer.instrument}`  \n"
                f"**Retention stage** `{offer.retention_stage}`  \n"
                + (f"**Bonus** {offer.bonus_mb:,} MB  \n" if offer.bonus_mb else "")
                + (
                    f"**Valid** {offer.valid_from_hour:02d}:00-{offer.valid_to_hour:02d}:00  \n"
                    if offer.valid_from_hour is not None
                    else ""
                )
            )
            st.markdown(rtl(offer.customer_facing_reason_ar), unsafe_allow_html=True)
            st.caption(offer.customer_facing_reason_en)

        with st.expander("Guardrails considered"):
            st.dataframe(
                pd.DataFrame([c.model_dump() for c in offer.constraints]),
                width="stretch",
                hide_index=True,
            )
            st.caption(
                "Every guardrail that was CONSIDERED, not only those that bound. "
                "That is what makes the decision replayable."
            )
        st.caption(f"Decision log `{offer.decision_log_id}`")
    except Exception as exc:
        st.warning(f"Offer unavailable: {exc}", icon=":material/warning:")

with advance_column:
    st.subheader("Emergency advance")
    try:
        from cvm.api.schemas import AdvanceLimitRequest, AdvanceProduct
        from cvm.decision.advance_limit import decide_limit

        for product, label in (
            (AdvanceProduct.AIRTIME, "رصيد في وقته — airtime"),
            (AdvanceProduct.DATA, "نت في وقته — data, flat 5 LYD"),
        ):
            decision = decide_limit(
                AdvanceLimitRequest(subscriber_id=subscriber_id, product=product), features
            )
            if decision.approved:
                st.success(
                    f"**{label}** — {decision.limit_lyd:.0f} LYD  \n"
                    f"bound by `{decision.binding_constraint}`",
                    icon=":material/check_circle:",
                )
            else:
                extra = (
                    f"  \nFallback offered: `{decision.fallback_offer_id}`"
                    if decision.fallback_offer_id
                    else ""
                )
                st.error(
                    f"**{label}** — declined  \n"
                    f"bound by `{decision.binding_constraint}`{extra}",
                    icon=":material/block:",
                )
                st.markdown(rtl(decision.customer_facing_reason_ar), unsafe_allow_html=True)

        modal = number("modal_recharge_amount_lyd")
        if modal and modal <= 5:
            st.warning(
                f"**At the recharge floor.** This subscriber's modal top-up is "
                f"{modal:.0f} LYD — the smallest card sold. A 5 LYD data advance would "
                "consume the whole of it and return them to zero, so the recharge buys "
                "them nothing. That is the disincentive M4 exists to interrupt.",
                icon=":material/warning:",
            )
    except Exception as exc:
        st.warning(f"Advance decision unavailable: {exc}", icon=":material/warning:")

# --- Leakage ----------------------------------------------------------------
st.divider()
st.subheader("Share-of-wallet leakage")

ratio = number("incoming_outgoing_ratio")
left, middle, right = st.columns(3)
left.metric(
    "Incoming / outgoing",
    f"{ratio:.2f}",
    help="Above 1.0 means they receive more than they place -- a receiving SIM.",
)
middle.metric("On-net share", f"{number('onnet_ratio'):.1%}")
right.metric("Leakage score", f"{number('leakage_score'):.2f}")

if ratio > 1.0:
    st.warning(
        "**Receiving SIM.** Other people still call them; they do their calling "
        "elsewhere. Conventional churn models score this subscriber as retained — in "
        "revenue terms they are half-lost. The hypothesis is specific to dual-SIM "
        "prepaid and is **testable only on real Libyan data**; Cell2Cell shows no "
        "separation, which is what a single-SIM postpaid market should look like.",
        icon=":material/sim_card:",
    )
