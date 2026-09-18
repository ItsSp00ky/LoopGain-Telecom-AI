# Model Card — <Model name>

**Deliverable D10.** One per model. Copy this file, do not edit it in place.

Filling this in is item 5 of the Definition of Done. A model without a card is
not finished, however good its metrics are.

---

| | |
|---|---|
| **Module** | M? |
| **Version** | |
| **Owner** | E? |
| **MLflow run** | |
| **Code** | `src/cvm/models/…` |
| **Config** | `conf/models/….yaml` |
| **Trained on** | local CPU |
| **Last updated** | |

## Intended use

What decision does this model feed, and who reads its output?

## Out-of-scope use

Where this model must **not** be used. Be specific — this section is the one an
evaluator reads most carefully.

For anything touching pricing or credit, state explicitly that the model
produces an input to a constrained decision, not the decision itself.

## Training data

| | |
|---|---|
| Source | Which datasets, real vs generated |
| Rows | Train / validation / test |
| Split | **Temporal.** State the cut dates. |
| Window | 90d observation → 15d gap → 30d outcome |
| Class balance | |
| Excluded fields | Which, and why |

Note any preprocessing that materially changes the data: deduplication,
resampling, reject inference, quantile mapping.

## Metrics

Report the **primary** metric first. Accuracy is not a headline metric at a
10–30% base rate; if you report it at all, report it last and say why it is
uninformative.

| Metric | Value | Notes |
|---|---|---|
| PR-AUC | | primary |
| Lift @ decile 1 | | |
| Brier score | | calibration |
| ROC-AUC | | secondary |

### Naive vs honest

Where a naive setup (duplicates retained, leaky features kept, random split)
produces a different number, show both and explain the gap. This is a project
commitment, not an optional extra.

| Setup | PR-AUC | ROC-AUC | Note |
|---|---|---|---|
| Naive | | | |
| Honest | | | |

## Calibration

Which method, fitted on which slice, and the reliability diagram. If this model
feeds the pricing engine, calibration is mandatory — a probability consumed as
a monetary expectation must mean what it says.

## Explainability

What explanation does this model produce, for whom, and in what form? If the
answer is "none", say so and say what is compared instead.

## Limitations

Be direct. Known failure modes, populations where performance degrades, and
anything the training data could not represent.

**Every card must state:** metrics are computed on generated data and are not
evidence of production performance. The real-data validation path required
before any deployment decision is in the proposal, §6.5.

## Ethical considerations

- Protected attributes used, if any, and for what — relevance is not pricing.
- Fairness audit performed, and its result.
- Who is harmed if this model is wrong, and in which direction.
- For M4 specifically: the line-survival objective, chronic-distress exclusion,
  cooling-off periods, and the Shariah-review flag on fee structure.

## Selection bias

If the training population was filtered by an existing business rule, name the
rule and say what was done about it. (M4: repayment is only observed for
subscribers who were granted an advance.)

## Maintenance

- Retraining trigger:
- Drift monitoring: Evidently report at `artifacts/reports/…`
- Who to contact:
