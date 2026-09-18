# Model Cards

Deliverable D10: one card per model. Copy [TEMPLATE.md](TEMPLATE.md), do not
edit it in place.

A card is item 5 of the Definition of Done. A model without a card is not
finished, however good its metrics are.

| Card | Module | Owner | Status |
|---|---|---|---|
| [m1-churn-lightgbm.md](m1-churn-lightgbm.md) | M1 | E2 | not started |
| [m1b-survival.md](m1b-survival.md) | M1b time-to-churn | E2 | not started |
| [m2-clv.md](m2-clv.md) | M2 CLV | E3 | not started |
| [m4-repayment-pd.md](m4-repayment-pd.md) | M4 | E2 | not started |

These files are also part of the RAG corpus published to the Employee Copilot
and Customer Chatbot (see ../INTEGRATION.md), which is how those agents answer
"why did this subscriber get this offer?" by citing the actual rule rather than
inventing a plausible one. Keep them accurate -- a stale card becomes a
confidently wrong answer in someone else's demo.