"""Pandera schema contracts for every source and every landed table.

These run in CI (the `schema` job). A contract here is the machine-readable
half of docs/data_dictionary.md -- if you change one, change the other in the
same PR.
"""

from __future__ import annotations

import pandera as pa
from pandera.typing import Series


class UciIranianRaw(pa.DataFrameModel):
    """Dataset A as downloaded, before dedup and before dropping the leaky field."""

    # TODO(E1): the 13 source features + Churn label.
    # Note: "Customer Value" is validated here but MUST be excluded from the
    # feature matrix -- it partially encodes the outcome. See features.yaml.

    class Config:
        strict = False
        coerce = True


class Cell2CellRaw(pa.DataFrameModel):
    """Dataset B as downloaded. 58 features; changem/changer are the decay ancestors."""

    class Config:
        strict = False
        coerce = True


class IbmTelcoRaw(pa.DataFrameModel):
    """Dataset C as downloaded. Carries CLTV, Churn Reason and Churn Score."""

    class Config:
        strict = False
        coerce = True


class SubscriberSnapshot(pa.DataFrameModel):
    """The landed, hashed, per-subscriber snapshot every downstream layer reads."""

    subscriber_id_hashed: Series[str] = pa.Field(str_matches=r"^[0-9a-f]{64}$", unique=True)
    snapshot_date: Series[pa.DateTime]

    class Config:
        strict = False
        coerce = True