"""Loading the raw prepaid export and naming its monthly columns."""

import re
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_TRAIN_PATH = PROJECT_ROOT / "data" / "raw" / "train.csv"
REPORTS_DIR = PROJECT_ROOT / "reports"

FEATURE_MONTHS = (6, 7, 8)
LABEL_COLUMN = "churn_probability"
ID_COLUMNS = ("id", "mobile_number")

_MONTH_SUFFIX = re.compile(r"^(?P<base>.+)_(?P<month>[6-9])$")
_MONTH_PREFIX = re.compile(r"^(?P<month>jun|jul|aug|sep)_(?P<base>.+)$")
_MONTH_NAMES = {"jun": 6, "jul": 7, "aug": 8, "sep": 9}
_MONTH_PREFIXED_BASES = {"vbc_3g"}
_DATE_FORMATS = ("%m/%d/%Y", "%Y-%m-%d")


def load_raw(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Download train.csv as described in README.md (section Data)."
        )
    # Identifiers are opaque: inference would drop leading zeros and treat "NA" as missing.
    return pd.read_csv(path, converters=dict.fromkeys(ID_COLUMNS, str))


def split_month(column: str) -> tuple[str, int | None]:
    """Return a column's base name and month, or (column, None) for non-monthly columns.

    Most monthly columns end in `_6` to `_9`; the volume-based-cost columns start
    with a month name instead (`jun_vbc_3g`).
    """
    if match := _MONTH_SUFFIX.match(column):
        return match["base"], int(match["month"])
    if match := _MONTH_PREFIX.match(column):
        return match["base"], _MONTH_NAMES[match["month"]]
    return column, None


def column_name(base: str, month: int) -> str:
    """Inverse of `split_month`: the real column name for a base name and month."""
    if base in _MONTH_PREFIXED_BASES:
        prefix = next(name for name, number in _MONTH_NAMES.items() if number == month)
        return f"{prefix}_{base}"
    return f"{base}_{month}"


def parse_dates(values: pd.Series) -> pd.Series:
    """Parse export dates written as month/day/year (Kaggle) or year-month-day (ISO).

    Anything that fits neither format becomes NaT.
    """
    parsed = pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns]")
    for date_format in _DATE_FORMATS:
        attempt = pd.to_datetime(values, format=date_format, errors="coerce")
        parsed = parsed.fillna(attempt)
    return parsed


def monthly_columns(columns) -> pd.DataFrame:
    """One row per base name, one column per month, holding the real column name."""
    rows: dict[str, dict[int, str]] = {}
    for column in columns:
        base, month = split_month(column)
        if month is not None:
            rows.setdefault(base, {})[month] = column
    return pd.DataFrame.from_dict(rows, orient="index").sort_index().sort_index(axis=1)


def id_column(df: pd.DataFrame) -> str:
    for column in ID_COLUMNS:
        if column in df.columns:
            return column
    raise ValueError(f"No customer id column found; expected one of {ID_COLUMNS}.")
