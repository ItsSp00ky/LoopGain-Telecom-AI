"""AI Customer Value Management Suite.

A decision-intelligence layer over prepaid telecom telemetry for the Libyan
market. See docs/proposal/AI_CVM_Suite_SIC_Proposal_v2.md for the full spec.

Layers
------
ingest      Layer 1 -- load, validate, deduplicate, hash identifiers
synthesis   Layer 2 -- CTGAN / TVAE / Copula + SDMetrics quality gate
features    Layer 3 -- RFM-LE, decay, leakage, sequences, DuckDB feature store
models      Layer 4 -- M1 churn, M2 value, M4 advance
decision    Layer 5 -- pricing, uplift, advance limit, guardrails  (the core)
api         Layer 6 -- FastAPI serving, and the platform integration surface

This is `ali_branch`: Component 3 of a five-component telecom AI platform.
The Employee Copilot and Customer Chatbot are separate components owned by
other team members. They consume this package's API over HTTP, read-only.
There is deliberately no agent and no LLM call path in this package.
See docs/INTEGRATION.md.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
