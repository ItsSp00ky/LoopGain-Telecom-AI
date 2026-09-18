"""Business-rule overlays: the constructs real data cannot supply.

Seasonal offers published by Libyan operators confirm these cycles are real
commercial events rather than local colour we invented.

Two overlays are anchored to confirmed Almadar products rather than guessed:
the 06:00-11:00 morning usage bump (عروض الصبح exists and is time-boxed to
exactly that window), and emergency-credit behaviour for both رصيد في وقته
and نت في وقته. See conf/catalogue.yaml.
"""

from __future__ import annotations

import pandas as pd


def apply_service_outage_exposure(df: pd.DataFrame) -> pd.DataFrame:
    """Power- and fuel-driven downtime, at SUBSCRIBER level.

    No geographic variation: all subscribers are drawn from one distribution.
    Geography was dropped, so there are no districts to weight by.
    """
    raise NotImplementedError("TODO(E1)")


def apply_ramadan_seasonality(df: pd.DataFrame) -> pd.DataFrame:
    raise NotImplementedError("TODO(E1)")


def apply_salary_week_spike(df: pd.DataFrame) -> pd.DataFrame:
    """Public-sector salary disbursement drives a pronounced recharge spike."""
    raise NotImplementedError("TODO(E1)")


def apply_emergency_credit_behaviour(df: pd.DataFrame) -> pd.DataFrame:
    """Generate the M4 label surface for both Almadar emergency products.

    Fields: airtime_advance_count_90d, data_advance_count_90d, days_to_settle,
    unpaid_advance_days, emergency_service_alternations_90d.

    Three things the overlay MUST reproduce, or M4 has nothing to find:

    1. Eligibility is balance-based, not tenure-based. Advances happen when
       balance falls to <= 0.5 LYD (airtime) or <= 1 LYD with < 250 MB left
       (data). The eligible population is therefore selected on being broke.
    2. The 5 LYD data advance exceeds the 3 LYD smallest recharge card, so a
       habitual small-card recharger cannot clear it in one top-up. Some
       subscribers must end up with persistent unpaid debt.
    3. The two products are mutually exclusive, so distressed subscribers
       alternate between them. That alternation must be visible in the data.
    """
    raise NotImplementedError("TODO(E1/E2)")


def apply_morning_offpeak_usage(df: pd.DataFrame) -> pd.DataFrame:
    """Put a 06:00-11:00 usage bump on subscribers who buy عروض الصبح.

    Without this, offpeak_data_ratio is noise and M3 cannot tell who would
    actually use a morning pass.
    """
    raise NotImplementedError("TODO(E1)")