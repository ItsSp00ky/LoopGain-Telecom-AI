"""Input data contract for a prepaid monthly export (ticket T2).

The column groups below are the single source of truth: the pandera schema, the
cleaning rules (T3) and `docs/data_contract.md` are all built from them. An
operator export (for example Libyana or Al-Madar) is usable when it passes
`validate`.
"""

from dataclasses import dataclass

import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaErrors

from prepaid_churn.data import FEATURE_MONTHS, LABEL_COLUMN, column_name, parse_dates

ID = "id"
TENURE = "aon"


@dataclass(frozen=True)
class ColumnGroup:
    name: str
    bases: tuple[str, ...]
    kind: str  # "amount", "count", "signed", "flag" or "date"
    nullable: bool
    meaning: str


GROUPS = (
    ColumnGroup(
        "Voice minutes",
        (
            "onnet_mou",
            "offnet_mou",
            "roam_ic_mou",
            "roam_og_mou",
            "loc_og_t2t_mou",
            "loc_og_t2m_mou",
            "loc_og_t2f_mou",
            "loc_og_t2c_mou",
            "loc_og_mou",
            "std_og_t2t_mou",
            "std_og_t2m_mou",
            "std_og_t2f_mou",
            "std_og_mou",
            "isd_og_mou",
            "spl_og_mou",
            "og_others",
            "loc_ic_t2t_mou",
            "loc_ic_t2m_mou",
            "loc_ic_t2f_mou",
            "loc_ic_mou",
            "std_ic_t2t_mou",
            "std_ic_t2m_mou",
            "std_ic_t2f_mou",
            "std_ic_mou",
            "spl_ic_mou",
            "isd_ic_mou",
            "ic_others",
        ),
        "amount",
        True,
        "Minutes by call type: on-net/off-net, roaming, local/STD/international, "
        "incoming (ic) and outgoing (og). The whole block is missing in a month "
        "without any voice record, which means no calls.",
    ),
    ColumnGroup(
        "Voice totals",
        ("total_og_mou", "total_ic_mou"),
        "amount",
        False,
        "Total outgoing and incoming minutes.",
    ),
    ColumnGroup(
        "Data usage",
        ("vol_2g_mb", "vol_3g_mb", "vbc_3g"),
        "amount",
        False,
        "Mobile data volume in MB, and pay-per-use data cost (vbc) without a pack.",
    ),
    ColumnGroup(
        "Revenue",
        ("arpu",),
        "signed",
        False,
        "Average revenue per user. Can be negative after billing adjustments.",
    ),
    ColumnGroup(
        "Recharges",
        ("total_rech_num", "total_rech_amt", "max_rech_amt", "last_day_rch_amt"),
        "count",
        False,
        "Number of recharges, total and largest recharge amount, and the amount on "
        "the last recharge day (local currency).",
    ),
    ColumnGroup(
        "Pack counts",
        ("monthly_2g", "sachet_2g", "monthly_3g", "sachet_3g"),
        "count",
        False,
        "Number of monthly packs and short-validity (sachet) packs bought.",
    ),
    ColumnGroup(
        "Last recharge date",
        ("date_of_last_rech",),
        "date",
        True,
        "Date of the last recharge in the month. Missing exactly when there was "
        "no recharge (total_rech_num is 0).",
    ),
    ColumnGroup(
        "Data recharges",
        ("total_rech_data", "max_rech_data", "count_rech_2g", "count_rech_3g", "av_rech_amt_data"),
        "amount",
        True,
        "Data pack recharges: count, largest and average amount, 2G and 3G counts.",
    ),
    ColumnGroup(
        "Data revenue",
        ("arpu_2g", "arpu_3g"),
        "signed",
        True,
        "Revenue from 2G and 3G data. Can be negative after billing adjustments.",
    ),
    ColumnGroup(
        "Pack user flags",
        ("night_pck_user", "fb_user"),
        "flag",
        True,
        "1 if the subscriber used a night pack or a social-network pack.",
    ),
    ColumnGroup(
        "Last data recharge date",
        ("date_of_last_rech_data",),
        "date",
        True,
        "Date of the last data pack recharge in the month.",
    ),
    ColumnGroup(
        "Month end",
        ("last_date_of_month",),
        "date",
        True,
        "Last day of the month, the reference date for recency. Missing values are "
        "allowed as long as some rows carry the date.",
    ),
)

# The data block goes missing as a whole in a month without any data recharge.
DATA_BLOCK_GROUPS = ("Data recharges", "Data revenue", "Pack user flags", "Last data recharge date")


def group(name: str) -> ColumnGroup:
    return next(g for g in GROUPS if g.name == name)


VOICE_BLOCK = group("Voice minutes").bases
DATA_BLOCK = tuple(base for name in DATA_BLOCK_GROUPS for base in group(name).bases)


def monthly_contract_columns(months=FEATURE_MONTHS) -> list[str]:
    return [column_name(base, month) for month in months for g in GROUPS for base in g.bases]


class InvalidExportError(ValueError):
    """The export does not match the data contract; the message lists every problem."""


def _date_in_month(month: int) -> pa.Check:
    def check(values: pd.Series) -> pd.Series:
        return parse_dates(values).dt.month.eq(month)

    return pa.Check(check, name=f"date in month {month}")


def _column(kind: str, nullable: bool, month: int) -> pa.Column:
    if kind == "amount":
        return pa.Column(float, pa.Check.ge(0), nullable=nullable, coerce=True)
    if kind == "count":
        return pa.Column(int, pa.Check.ge(0), nullable=nullable, coerce=True)
    if kind == "signed":
        return pa.Column(float, nullable=nullable, coerce=True)
    if kind == "flag":
        return pa.Column(float, pa.Check.isin([0, 1]), nullable=nullable, coerce=True)
    return pa.Column(nullable=nullable, checks=_date_in_month(month))


def _missing_together(bases: tuple[str, ...], month: int, name: str) -> pa.Check:
    columns = [column_name(base, month) for base in bases]

    def check(df: pd.DataFrame) -> pd.Series | bool:
        if not set(columns) <= set(df.columns):
            return True  # missing columns are reported by their own checks
        missing = df[columns].isna()
        return missing.all(axis=1) | ~missing.any(axis=1)

    return pa.Check(check, name=f"{name} missing together in month {month}")


def _recharge_date_matches_count(month: int) -> pa.Check:
    date, count = column_name("date_of_last_rech", month), column_name("total_rech_num", month)

    def check(df: pd.DataFrame) -> pd.Series | bool:
        if not {date, count} <= set(df.columns):
            return True
        return df[date].isna() == df[count].eq(0)

    return pa.Check(check, name=f"recharge date missing only without recharges in month {month}")


def _month_end_present(month: int) -> pa.Check:
    column = column_name("last_date_of_month", month)

    def check(df: pd.DataFrame) -> bool:
        return column not in df.columns or bool(df[column].notna().any())

    return pa.Check(check, name=f"month end date present in month {month}")


def build_schema(months=FEATURE_MONTHS, labeled: bool = False) -> pa.DataFrameSchema:
    columns = {
        ID: pa.Column(unique=True),  # a number or text: operators may export a salted hash
        TENURE: pa.Column(int, pa.Check.ge(0), coerce=True),
    }
    if labeled:
        columns[LABEL_COLUMN] = pa.Column(int, pa.Check.isin([0, 1]), coerce=True)
    checks = []
    for month in months:
        for g in GROUPS:
            for base in g.bases:
                columns[column_name(base, month)] = _column(g.kind, g.nullable, month)
        checks += [
            _missing_together(VOICE_BLOCK, month, "voice block"),
            _missing_together(DATA_BLOCK, month, "data block"),
            _recharge_date_matches_count(month),
            _month_end_present(month),
        ]
    return pa.DataFrameSchema(columns, checks=checks, strict=False)


def summarize_failures(failure_cases: pd.DataFrame, subject: str) -> str:
    """One readable message listing every failed pandera check, grouped by column and check."""
    lines = []
    for (column, check), cases in failure_cases.groupby(
        [failure_cases["column"].fillna("rows"), "check"], sort=False
    ):
        examples = ", ".join(map(str, cases["failure_case"].dropna().unique()[:3]))
        lines.append(f"- {column}: {check} failed {len(cases)} times (examples: {examples})")
    return f"{subject} ({len(lines)} problems):\n" + "\n".join(lines)


def validate(df: pd.DataFrame, months=FEATURE_MONTHS, labeled: bool | None = None) -> pd.DataFrame:
    """Return the export with contract dtypes, or raise InvalidExportError listing every problem.

    `labeled` defaults to whether the label column is present.
    """
    if labeled is None:
        labeled = LABEL_COLUMN in df.columns
    try:
        return build_schema(months, labeled).validate(df, lazy=True)
    except SchemaErrors as errors:
        raise InvalidExportError(
            summarize_failures(errors.failure_cases, "The export does not match the data contract")
        ) from None


def contract_markdown(months=FEATURE_MONTHS) -> str:
    """The data contract as Markdown, generated from GROUPS."""
    kinds = {
        "amount": "number >= 0",
        "count": "whole number >= 0",
        "signed": "number",
        "flag": "0 or 1",
        "date": "date (m/d/yyyy or yyyy-mm-dd) inside its month",
    }
    month_list = ", ".join(map(str, months))
    lines = [
        "# Data contract: prepaid monthly export",
        "",
        "Generated by `uv run churn contract` from `src/prepaid_churn/schema.py`.",
        "Do not edit it by hand.",
        "",
        "One row per subscriber.",
        f"Monthly columns end with the month number (`_{months[0]}`), except `vbc_3g`, which "
        "starts with the month name (`jun_vbc_3g`).",
        f"The Kaggle training data uses months {month_list} (June to August 2014).",
        "Extra columns are allowed and ignored.",
        "`uv run churn validate --input <file>` checks an export against this contract.",
        "",
        "## Subscriber columns",
        "",
        "| Column | Type | Missing allowed | Meaning |",
        "|---|---|---|---|",
        f"| `{ID}` | number or text, unique | no | Pseudonymous subscriber identifier, "
        "for example a salted hash of the phone number; never the phone number itself "
        "(decision 17). |",
        f"| `{TENURE}` | whole number >= 0 | no | Age on network in days. |",
        f"| `{LABEL_COLUMN}` | 0 or 1 | no | Training data only: 1 if the subscriber "
        "churned in the month after the last feature month. |",
        "",
        "## Monthly columns",
        "",
        "| Group | Base columns | Type | Missing allowed | Meaning |",
        "|---|---|---|---|---|",
    ]
    for g in GROUPS:
        bases = ", ".join(f"`{base}`" for base in g.bases)
        missing = "yes" if g.nullable else "no"
        lines.append(f"| {g.name} | {bases} | {kinds[g.kind]} | {missing} | {g.meaning} |")
    lines += [
        "",
        "## Row rules",
        "",
        "- The voice minutes block is either complete or entirely missing in a month.",
        f"- The data block ({', '.join(DATA_BLOCK_GROUPS)}) is either complete or entirely "
        "missing in a month.",
        "- `date_of_last_rech` is missing exactly when `total_rech_num` is 0.",
        "- Every month has at least one row with `last_date_of_month`.",
        "",
        "Missing values in both blocks mean zero activity; cleaning (T3) turns them into 0.",
        "",
        "## Adapting a Libyan export",
        "",
        'The source data comes from an operator with regional "circles": `loc` means calls '
        "inside the subscriber's circle and `std` calls outside it.",
        "A Libyan export can map national calls to `loc` and leave `std` at 0, or define "
        "regions (for example by municipality) to keep the split.",
        "Amounts are in local currency (LYD for a Libyan export).",
        "",
    ]
    return "\n".join(lines)
