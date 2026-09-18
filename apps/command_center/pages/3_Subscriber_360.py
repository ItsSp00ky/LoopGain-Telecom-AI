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

import streamlit as st

st.title("Subscriber 360")

subscriber_id = st.text_input(
    "Subscriber ID (salted SHA-256 hash)",
    placeholder="64 hex characters",
    help="No raw MSISDN is accepted anywhere in this system.",
)

st.warning("Not implemented yet -- E5, sprint day 10.", icon=":material/construction:")

# TODO(E5): GET /v1/subscriber/{id}. Render the SHAP waterfall with the
# plain_language field, not the raw feature names -- "has not topped up in 23
# days", not "days_since_last_topup = 23". Show the advance limit's
# binding_constraint so the reason is visible, not just the number.