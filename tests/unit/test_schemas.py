"""API contracts. These are frozen on sprint day 3 -- breaking one is a
cross-team event, so it should break a test first."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cvm.api.schemas import ChurnScoreRequest, TextClassifyRequest

VALID_ID = "a" * 64


def test_subscriber_id_must_be_a_64_char_hex_digest():
    ChurnScoreRequest(subscriber_ids=[VALID_ID])


@pytest.mark.parametrize(
    "bad",
    [
        "0912345678",            # a raw MSISDN must not validate
        "a" * 63,                # too short
        "a" * 65,                # too long
        "A" * 64,                # uppercase: normalise before calling
        "not-a-hash",
    ],
)
def test_subscriber_id_rejects_non_hashes(bad: str):
    with pytest.raises(ValidationError):
        ChurnScoreRequest(subscriber_ids=[bad])


def test_batch_size_is_capped():
    with pytest.raises(ValidationError):
        ChurnScoreRequest(subscriber_ids=[VALID_ID] * 10_001)


def test_unknown_fields_are_rejected():
    """extra="forbid" so a typo'd field name fails instead of being ignored."""
    with pytest.raises(ValidationError):
        ChurnScoreRequest(subscriber_ids=[VALID_ID], armm="arm_a_lightgbm")


def test_text_classify_requires_at_least_one_text():
    with pytest.raises(ValidationError):
        TextClassifyRequest(texts=[])