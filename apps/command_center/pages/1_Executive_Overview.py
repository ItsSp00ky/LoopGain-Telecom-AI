"""Screen 1 -- Executive Overview.  Owner: E5

Subscribers at risk (30d), revenue at risk in LYD, base composition by tier,
churn trend, and a retained-revenue simulation against a do-nothing baseline.

The do-nothing baseline is the point of the screen: it is what turns a model
metric into a number an executive can act on.
"""

from __future__ import annotations

import streamlit as st

st.title("Executive Overview")
st.warning("Not implemented yet -- E5, sprint day 10.", icon=":material/construction:")

# TODO(E5): POST /v1/cohort/query for the LYD headline; feature store for base
# composition; M1 scores by decile for the risk distribution.