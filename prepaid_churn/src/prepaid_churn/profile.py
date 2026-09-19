"""Data profiling for the raw prepaid export (ticket T1).

Every function answers one T1 question and is pure, so it can be tested on tiny
hand-made frames. `build_report` assembles the answers into Markdown.
"""

import pandas as pd

from prepaid_churn.data import FEATURE_MONTHS, LABEL_COLUMN, id_column, monthly_columns
from prepaid_churn.labels import recharge_inactive, usage_inactive

# A minute column that goes missing whenever a month has no voice activity record.
MINUTES_REFERENCE = "onnet_mou"
# Missing exactly when the customer bought no data pack that month, if the zero hypothesis holds.
DATA_RECHARGE_REFERENCE = "date_of_last_rech_data"


def missing_by_month(df: pd.DataFrame) -> pd.DataFrame:
    """Share of missing values per monthly base column, one column per month."""
    table = monthly_columns(df.columns)
    return table.map(lambda name: df[name].isna().mean() if isinstance(name, str) else None)


def missing_agreement(df: pd.DataFrame, reference: str) -> pd.DataFrame:
    """Share of rows whose missingness matches the `reference` base column, per month.

    Only columns that have missing values in that month are compared. A share of
    1.0 means the column is missing exactly when the reference is missing.
    """
    table = monthly_columns(df.columns)
    if reference not in table.index:
        return pd.DataFrame()
    result: dict[str, dict[int, float]] = {}
    for month in table.columns:
        reference_name = table.at[reference, month]
        if not isinstance(reference_name, str):
            continue
        reference_missing = df[reference_name].isna()
        for base, name in table[month].dropna().items():
            missing = df[name].isna()
            if base != reference and missing.any():
                result.setdefault(base, {})[month] = (missing == reference_missing).mean()
    return pd.DataFrame.from_dict(result, orient="index").sort_index()


def zero_usage_when_minutes_missing(df: pd.DataFrame) -> pd.DataFrame:
    """Per month: customers whose minute columns are missing, and how many of them have zero totals.

    If missing minutes mean "no calls", total incoming and outgoing minutes should be 0 for them.
    """
    rows = {}
    for month in FEATURE_MONTHS:
        missing = df[f"{MINUTES_REFERENCE}_{month}"].isna()
        totals = df.loc[missing, [f"total_ic_mou_{month}", f"total_og_mou_{month}"]]
        rows[month] = {
            "customers_with_missing_minutes": int(missing.sum()),
            "share_with_zero_totals": totals.fillna(0).eq(0).all(axis=1).mean()
            if missing.any()
            else None,
        }
    return pd.DataFrame.from_dict(rows, orient="index")


def constant_columns(df: pd.DataFrame) -> list[str]:
    """Columns with at most one distinct non-missing value: they carry no information."""
    return [column for column in df.columns if df[column].nunique() <= 1]


def duplicates(df: pd.DataFrame) -> dict[str, int]:
    key = id_column(df)
    return {
        "duplicate_ids": int(df[key].duplicated().sum()),
        "duplicate_rows_ignoring_id": int(df.drop(columns=key).duplicated().sum()),
    }


def negative_values(df: pd.DataFrame) -> pd.DataFrame:
    """Numeric columns that contain negative values, with how many and the minimum."""
    numeric = df.select_dtypes("number")
    counts = numeric.lt(0).sum()
    counts = counts[counts > 0]
    return pd.DataFrame({"negative_rows": counts, "minimum": numeric[counts.index].min()})


def inactivity_by_month(df: pd.DataFrame) -> pd.DataFrame:
    """Usage-based vs recharge-based inactivity per feature month, and how they overlap."""
    rows = {}
    for month in FEATURE_MONTHS:
        usage = usage_inactive(df, month)
        recharge = recharge_inactive(df, month)
        rows[month] = {
            "usage_inactive": usage.mean(),
            "recharge_inactive": recharge.mean(),
            "both": (usage & recharge).mean(),
            "usage_only": (usage & ~recharge).mean(),
            "recharge_only": (~usage & recharge).mean(),
        }
    return pd.DataFrame.from_dict(rows, orient="index")


def label_vs_month_8(df: pd.DataFrame) -> dict[str, float]:
    """How the month 9 churn label relates to inactivity already visible in month 8."""
    churned = df[LABEL_COLUMN].eq(1)
    inactive_8 = usage_inactive(df, 8)
    return {
        "label_rate": churned.mean(),
        "churners_already_inactive_in_month_8": inactive_8[churned].mean(),
        "label_rate_if_inactive_in_month_8": churned[inactive_8].mean(),
        "label_rate_if_active_in_month_8": churned[~inactive_8].mean(),
    }


def _format(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def markdown_table(frame: pd.DataFrame, index_name: str = "") -> str:
    header = [index_name, *map(str, frame.columns)]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    # itertuples keeps each column's dtype, so counts stay integers next to float shares.
    for index, *values in frame.itertuples(name=None):
        lines.append("| " + " | ".join([str(index), *map(_format, values)]) + " |")
    return "\n".join(lines)


def build_report(df: pd.DataFrame) -> str:
    missing = missing_by_month(df)
    with_missing = missing[missing.fillna(0).max(axis=1) > 0]
    sections = [
        "# T1 data profile",
        "",
        "Generated by `uv run churn profile`. Shares are fractions of all customers (0.10 = 10%).",
        "",
        f"Rows: {len(df)}. Columns: {df.shape[1]}. "
        f"Monthly base columns: {len(missing)}, of which {len(with_missing)} have missing values.",
        "",
        "## Missing values per monthly column",
        "",
        markdown_table(with_missing.sort_values(list(with_missing.columns), ascending=False)),
        "",
        f"## Do columns go missing together with `{MINUTES_REFERENCE}`?",
        "",
        "1.0 means the column is missing exactly when the reference is missing.",
        "",
        markdown_table(missing_agreement(df, MINUTES_REFERENCE)),
        "",
        "## Are totals zero when minute columns are missing?",
        "",
        markdown_table(zero_usage_when_minutes_missing(df), "month"),
        "",
        f"## Do data recharge columns go missing together with `{DATA_RECHARGE_REFERENCE}`?",
        "",
        markdown_table(missing_agreement(df, DATA_RECHARGE_REFERENCE)),
        "",
        "## Constant columns",
        "",
        ", ".join(f"`{column}`" for column in constant_columns(df)) or "None.",
        "",
        "## Duplicates",
        "",
        *[f"- {name}: {count}" for name, count in duplicates(df).items()],
        "",
        "## Negative values",
        "",
        markdown_table(negative_values(df), "column"),
        "",
        "## Inactivity per month (missing counted as zero)",
        "",
        markdown_table(inactivity_by_month(df), "month"),
    ]
    if LABEL_COLUMN in df.columns:
        sections += [
            "",
            "## Month 9 label vs month 8 inactivity",
            "",
            *[f"- {name}: {_format(value)}" for name, value in label_vs_month_8(df).items()],
        ]
    return "\n".join(sections) + "\n"
