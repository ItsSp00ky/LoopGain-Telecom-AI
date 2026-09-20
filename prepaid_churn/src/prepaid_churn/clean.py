"""Cleaning rules for a validated prepaid export (ticket T3).

Every rule comes from the T1 findings in TICKETS.md. `clean` is idempotent:
cleaning an already cleaned frame changes nothing. Negative ARPU values are kept
on purpose; they are billing adjustments, not errors.
"""

import pandas as pd

from prepaid_churn.data import FEATURE_MONTHS, LABEL_COLUMN, column_name, parse_dates
from prepaid_churn.schema import DATA_BLOCK, ID, TENURE, VOICE_BLOCK, monthly_contract_columns

NO_VOICE_FLAG = "no_voice_record"
MONTH_END = "last_date_of_month"
# Date column -> days from that date to the month end.
RECENCY = {
    "date_of_last_rech": "days_since_last_rech",
    "date_of_last_rech_data": "days_since_last_rech_data",
}


def derived_columns(months=FEATURE_MONTHS) -> list[str]:
    return [
        column_name(base, month) for month in months for base in (NO_VOICE_FLAG, *RECENCY.values())
    ]


def select_contract_columns(df: pd.DataFrame, months=FEATURE_MONTHS) -> pd.DataFrame:
    """Keep contract and derived columns in a fixed order; drop everything else.

    This removes the 13 no-information columns found in T1 and any extra
    columns an operator export may carry.
    """
    wanted = [ID, TENURE, LABEL_COLUMN, *monthly_contract_columns(months), *derived_columns(months)]
    return df[[column for column in wanted if column in df.columns]]


def flag_no_voice_record(df: pd.DataFrame, months=FEATURE_MONTHS) -> pd.DataFrame:
    """1 where the whole voice block of a month is missing, which means no calls that month."""
    df = df.copy()
    for month in months:
        flag = column_name(NO_VOICE_FLAG, month)
        if flag not in df.columns:
            voice = [column_name(base, month) for base in VOICE_BLOCK]
            df[flag] = df[voice].isna().all(axis=1).astype(int)
    return df


def fill_missing_as_zero(df: pd.DataFrame, months=FEATURE_MONTHS) -> pd.DataFrame:
    """Missing values in the voice and data blocks mean no activity, so they become 0."""
    blocks = [base for base in (*VOICE_BLOCK, *DATA_BLOCK) if base not in RECENCY]
    columns = [column_name(base, month) for month in months for base in blocks]
    return df.fillna({column: 0 for column in columns if column in df.columns})


def add_recency(df: pd.DataFrame, months=FEATURE_MONTHS) -> pd.DataFrame:
    """Replace recharge dates with days from the date to the month end.

    A month without a recharge gets the number of days in the month (30 for
    June), one more than any real value, so larger always means staler.
    """
    df = df.copy()
    for month in months:
        month_end_column = column_name(MONTH_END, month)
        if month_end_column not in df.columns:
            continue
        month_end = parse_dates(df[month_end_column]).mode().iloc[0]
        for date_base, recency_base in RECENCY.items():
            date_column = column_name(date_base, month)
            days = (month_end - parse_dates(df[date_column])).dt.days
            df[column_name(recency_base, month)] = days.fillna(month_end.day).astype(int)
            df = df.drop(columns=date_column)
        df = df.drop(columns=month_end_column)
    return df


def clean(df: pd.DataFrame, months=FEATURE_MONTHS) -> pd.DataFrame:
    """Apply every cleaning rule to an export that passed `schema.validate`."""
    df = select_contract_columns(df, months)
    df = flag_no_voice_record(df, months)
    df = fill_missing_as_zero(df, months)
    df = add_recency(df, months)
    return select_contract_columns(df, months).reset_index(drop=True)
