"""Shared fixtures.

Note the salt fixture: several tests exercise identifier hashing, and
cvm.config.Settings deliberately refuses to default the salt. Tests therefore
set a known one rather than the code providing a convenient fallback -- the
inconvenience is the point.
"""

from __future__ import annotations

import os

import pytest

TEST_SALT = "0" * 64


@pytest.fixture(autouse=True)
def _test_salt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every test a deterministic hash salt."""
    monkeypatch.setenv("CVM_HASH_SALT", TEST_SALT)
    from cvm.config import settings

    monkeypatch.setattr(settings, "hash_salt", TEST_SALT, raising=False)


@pytest.fixture
def seeded() -> int:
    from cvm.config import seed_everything

    return seed_everything(606)


@pytest.fixture
def offer_inputs() -> dict:
    """A well-behaved candidate offer that should pass every guardrail.

    Tests mutate one field at a time from this baseline, so a failure names the
    constraint that broke rather than leaving you to diff two dicts.
    """
    return dict(
        price_lyd=9.0,
        base_price_lyd=10.0,
        variable_cost_lyd=5.0,
        discount_pct=0.10,
        tier="silver",
        churn_probability=0.45,
        value_decile=5,
        predicted_clv_lyd=144.0,
        cumulative_spend_lyd_12m=0.0,
        pricing_features=["churn_probability", "loyalty_index", "price_sensitivity"],
    )