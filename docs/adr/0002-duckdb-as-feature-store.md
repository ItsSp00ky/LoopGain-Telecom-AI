# 0002 — DuckDB as the feature store

**Status:** accepted · **Date:** sprint day 3 · **Owner:** E1

## Context

We need an offline store for training and an online store for serving. The
obvious candidates were Postgres, a managed feature store (Feast), or embedded
analytical SQL.

Constraints: total budget under $40, `docker compose up` must reproduce the
system from a clean clone on a student laptop, and serving must fit in a
CPU-only container under 4 GB RAM.

## Decision

DuckDB, with Parquet for the offline layer.

## Consequences

**Good.** No database server to operate, back up or explain. One file that a
teammate can copy. Excellent analytical performance on this scale. It is also
opened read-only for serving, which is the simplest possible enforcement of
the no-write-path constraint in ADR 0004.

**Bad.** Single-writer. No concurrent write path, so nightly batch scoring must
not overlap serving. Not a production feature store: no point-in-time join
primitives, so `features/splits.py` implements that discipline itself and
`tests/leakage/` enforces it.

**This is the honest answer to "what breaks first at scale?"** DuckDB is correct
at demo scale; at 6M+ subscribers it becomes Spark or a columnar warehouse with
the same schema. Models and decision logic are unchanged, because nothing above
Layer 3 knows what the store is made of.