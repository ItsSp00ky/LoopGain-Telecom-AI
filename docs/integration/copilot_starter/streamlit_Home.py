"""CVM Copilot chat surface.  Owner: E5

Chat over the M7 LangChain agent, WITH VISIBLE TOOL-CALL TRACES so evaluators
can see it is grounded rather than hallucinating. The traces are a feature of
the demo, not a debug view to hide behind an expander nobody opens.

Rehearsed demo questions are in conf/models/m7_copilot.yaml.

Run:  streamlit run apps/copilot_ui/Home.py
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="CVM Copilot", page_icon="robot", layout="wide")

st.title("CVM Copilot")
st.caption(
    "Read-only. The Copilot queries the feature store, calls the scoring API and "
    "retrieves documentation. It does not set prices or credit limits -- those "
    "come from the decision engine under its guardrails."
)

question = st.chat_input("Ask about subscribers, risk, offers or sites...")
st.warning("Not implemented yet -- E5, sprint day 11.", icon=":material/construction:")

# TODO(E5): POST /v1/copilot/ask, render `tool_calls` inline above the answer,
# and show the cohort with an export button. If `grounded` is False, say so
# prominently instead of printing the answer as though it were sourced.