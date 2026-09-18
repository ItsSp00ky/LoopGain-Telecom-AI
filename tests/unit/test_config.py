"""Config loading and the guardrail accessor."""

from __future__ import annotations

import pytest

from cvm.config import guardrail, load_conf


def test_every_conf_file_parses():
    """A YAML syntax error must fail here, not at 2am on demo day."""
    for name in [
        "config",
        "data",
        "features",
        "pricing",
        "advance",
        "market",
        "catalogue",
        "models/m1_churn",
        "models/m2_value",
        "models/m3_uplift",
    ]:
        assert isinstance(load_conf(name), dict), name


def test_missing_config_lists_alternatives():
    with pytest.raises(FileNotFoundError, match="Available:"):
        load_conf("does_not_exist")


def test_guardrail_accessor_reads_nested_value():
    assert guardrail("pricing", "guardrails", "margin_floor", "min_margin") == pytest.approx(0.15)


def test_guardrail_accessor_raises_on_typo():
    """A mistyped guardrail path must not silently return None.

    Returning None would disable the guardrail without anyone noticing, which
    is the worst possible failure mode for this particular accessor.
    """
    with pytest.raises(KeyError, match="margin_flor"):
        guardrail("pricing", "guardrails", "margin_flor", "min_margin")


def test_tier_discount_ceilings_are_monotonic():
    """Bronze < Silver < Gold < Platinum. A loyalty ladder that is not
    monotonic is not a loyalty ladder."""
    tiers = load_conf("pricing")["tiers"]
    ordered = [tiers[t]["d_max"] for t in ("bronze", "silver", "gold", "platinum")]
    assert ordered == sorted(ordered)
    assert ordered == [0.05, 0.10, 0.15, 0.20]
