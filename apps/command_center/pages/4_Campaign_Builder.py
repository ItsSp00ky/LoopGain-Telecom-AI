"""Screen 4 -- Campaign Builder.  Owner: E5 (engine from E4)

Filter a cohort, set an LYD budget, run the uplift simulation, see expected
retained subscribers, cost and net margin, export a targeting CSV.

The control holdout is not optional and must be visible in the UI. Without it
there is no way to isolate net margin impact, which is exactly pain point P4 --
"net margin impact is never isolated because there is no holdout group".
"""

from __future__ import annotations

import streamlit as st

st.title("Campaign Builder")
st.warning("Not implemented yet -- E5, sprint day 11.", icon=":material/construction:")

# TODO(E5): cvm.decision.budget_lp.allocate for the cohort; show which
# guardrails bound and how many candidates each one rejected -- that is the
# most persuasive thing on the screen for an evaluator.