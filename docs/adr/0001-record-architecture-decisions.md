# 0001 — Record architecture decisions

**Status:** accepted · **Date:** sprint day 1 · **Owner:** E4

## Context

Six engineers, fifteen working days, seven modules. Several design choices in
this project are deliberate rejections of a more obvious option -- no ALS
recommender, no EconML, no contextual bandit, no CNN. An evaluator will ask
about at least one of them, and "we discussed it in week one" is not an answer.

## Decision

Record any non-obvious choice as a short ADR: context, decision, consequences.
One page. Numbered sequentially. Never edited after acceptance -- write a new
one that supersedes it.

## Consequences

- The report's methodology section largely writes itself from these files.
- The consuming components' RAG corpus gains the reasoning behind the design,
  not just its description.
- Small ongoing cost: roughly ten minutes per decision.