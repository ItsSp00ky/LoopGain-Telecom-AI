# 0003 — Two-model uplift instead of a causal-inference library

**Status:** accepted · **Date:** sprint day 8 · **Owner:** E4

## Context

Budget should go only to persuadables. The v1 proposal specified EconML for
heterogeneous treatment effects; the alternative is the classic two-model
difference -- fit a response model on the treated group and another on the
control group, and take the difference.

## Decision

Two-model difference. EconML is cut.

## Consequences

**Good.** Two models we already know how to build, validate and explain. The
method fits in one sentence of a three-minute pitch. No extra dependency, and
no extra failure mode in the final week.

**Bad.** Less statistically efficient, and no confidence intervals on the
treatment effect.

**Why the trade is right here.** The response surface is synthetic. The
additional precision EconML buys is precision about a treatment effect we
generated ourselves, so we could not validate it even if we measured it
carefully. Spending a sprint day on machinery whose output we cannot check is
worse than spending it on the guardrails, which we can.

Stated openly in the report rather than presented as a limitation we did not
notice. If real response data were available, this decision would be revisited
first.