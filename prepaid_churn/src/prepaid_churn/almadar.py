"""Almadar Aljadid packages and market facts (ticket T16, decision 16).

`data/almadar/offers.csv` lists what the operator sells, one row per package.
It is curated from the operator's own file in `data/almadar/source/`, and
`check_against_source` proves that every price, volume, minute count, member count
and speed the operator states still matches that file.
`data/almadar/market.toml` holds every other fact a calculation needs, each with a
status and a source. `docs/almadar.md` explains both files.
"""

import csv
import re
import tomllib
from pathlib import Path

import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaErrors

from prepaid_churn.data import PROJECT_ROOT
from prepaid_churn.schema import summarize_failures

ALMADAR_DIR = PROJECT_ROOT / "data" / "almadar"
OFFERS_PATH = ALMADAR_DIR / "offers.csv"
MARKET_PATH = ALMADAR_DIR / "market.toml"

OPERATORS = ("Almadar Aljadid",)
# Where a package's data volume comes from: the operator file states it, it is read from
# the package name ("نت 20" is 20 GB), a teammate reported it, or nobody knows it.
VOLUME_SOURCES = ("stated", "name", "reported", "none")
STATUSES = ("confirmed", "reported", "assumption", "estimate")

_UNLIMITED = {"لامحدودة", "غير محدودة", "لا محدودة"}
# Source columns: category, package, price, validity, data, minutes, upload, download, members.
_SOURCE_DATA = 4
_STATED = (
    ("voice_minutes", 5),
    ("max_upload_mbps", 6),
    ("max_download_mbps", 7),
    ("members", 8),
)


class InvalidCatalogueError(ValueError):
    """The catalogue or the market facts break a rule; the message lists every problem."""


def _flag() -> pa.Column:
    return pa.Column(int, pa.Check.isin([0, 1]), coerce=True)


def _optional_positive() -> pa.Column:
    return pa.Column(float, pa.Check.gt(0), nullable=True, coerce=True)


def _hour() -> pa.Column:
    return pa.Column(float, pa.Check.in_range(0, 24), nullable=True, coerce=True)


OFFERS_SCHEMA = pa.DataFrameSchema(
    {
        "offer_id": pa.Column(str, unique=True),
        "operator": pa.Column(str, pa.Check.isin(OPERATORS)),
        "family_ar": pa.Column(str),
        "family_en": pa.Column(str),
        "name_ar": pa.Column(str),
        "name_en": pa.Column(str),
        "price_lyd": pa.Column(float, pa.Check.gt(0), coerce=True),
        "validity_ar": pa.Column(str),
        "validity_hours": pa.Column(int, pa.Check.gt(0), coerce=True),
        "data_gb": _optional_positive(),
        "data_unlimited": _flag(),
        "volume_source": pa.Column(str, pa.Check.isin(VOLUME_SOURCES)),
        "voice_minutes": _optional_positive(),
        "voice_unlimited": _flag(),
        "members": _optional_positive(),
        "max_download_mbps": _optional_positive(),
        "max_upload_mbps": _optional_positive(),
        "network": pa.Column(str, nullable=True),
        "valid_from_hour": _hour(),
        "valid_to_hour": _hour(),
        "source_file": pa.Column(str),
        "source_row": pa.Column(int, pa.Check.gt(0), coerce=True),
        "collected": pa.Column(pa.DateTime, coerce=True),
        "notes": pa.Column(str, nullable=True),
    },
    checks=[
        pa.Check(
            lambda df: (df["data_unlimited"] == 0) | df["data_gb"].isna(),
            name="unlimited data has no volume",
        ),
        pa.Check(
            lambda df: (
                (df["volume_source"] == "none")
                == ((df["data_unlimited"] == 0) & df["data_gb"].isna())
            ),
            name="volume source is 'none' exactly when nothing is known about the volume",
        ),
        pa.Check(
            lambda df: (df["volume_source"] != "name") | df["data_gb"].notna(),
            name="a volume read from the name is a number",
        ),
        pa.Check(
            lambda df: (df["voice_unlimited"] == 0) | df["voice_minutes"].isna(),
            name="unlimited voice has no minute count",
        ),
        pa.Check(
            lambda df: df["valid_from_hour"].isna() == df["valid_to_hour"].isna(),
            name="a time window has both a start and an end",
        ),
        pa.Check(
            lambda df: df["valid_from_hour"].isna() | (df["valid_from_hour"] < df["valid_to_hour"]),
            name="a time window starts before it ends",
        ),
    ],
    strict=True,
)


def validate_offers(offers: pd.DataFrame) -> pd.DataFrame:
    """Return the catalogue with its dtypes, or raise InvalidCatalogueError listing all problems."""
    try:
        return OFFERS_SCHEMA.validate(offers, lazy=True)
    except SchemaErrors as errors:
        raise InvalidCatalogueError(
            summarize_failures(errors.failure_cases, "The Almadar catalogue breaks its rules")
        ) from None


def load_offers(path: str | Path = OFFERS_PATH) -> pd.DataFrame:
    return validate_offers(pd.read_csv(path, encoding="utf-8"))


def _number(text: str) -> float | None:
    match = re.search(r"\d+(?:\.\d+)?", text.replace("½", "0.5"))
    return float(match[0]) if match else None


def _stated_value(text: str) -> float | str | None:
    """A source cell as the catalogue stores it: a number, "unlimited", or None when empty."""
    text = text.strip()
    if text in _UNLIMITED:
        return "unlimited"
    return _number(text) if text else None


def _catalogue_value(offer: pd.Series, column: str) -> float | str | None:
    unlimited = {"data_gb": "data_unlimited", "voice_minutes": "voice_unlimited"}.get(column)
    if unlimited and offer[unlimited] == 1:
        return "unlimited"
    return None if pd.isna(offer[column]) else float(offer[column])


def check_against_source(offers: pd.DataFrame, directory: str | Path = ALMADAR_DIR) -> list[str]:
    """Problems where the catalogue no longer matches the operator's own file.

    Checks that every source row is covered exactly once, and that the family, name,
    price and every value the operator states (volume, minutes, speeds, members) match.
    A volume the file states must be marked "stated"; volumes it leaves out (read from
    the name or reported by a teammate) cannot be compared.
    """
    problems = []
    for source_file, rows in offers.groupby("source_file"):
        with (Path(directory) / source_file).open(encoding="utf-8-sig", newline="") as f:
            source = list(csv.reader(f))[1:]
        counts = rows["source_row"].value_counts()
        expected_rows = set(range(1, len(source) + 1))
        missing = sorted(expected_rows - set(counts.index))
        repeated = sorted(counts[counts > 1].index)
        unknown = sorted(set(counts.index) - expected_rows)
        if missing or repeated or unknown:
            problems.append(
                f"{source_file}: source rows missing {missing}, repeated {repeated}, "
                f"unknown {unknown}"
            )
            continue
        for _, offer in rows.iterrows():
            row = source[offer["source_row"] - 1]
            expected = {
                "family_ar": row[0].strip(),
                "name_ar": row[1].strip(),
                "price_lyd": _number(row[2]),
            }
            for column, index in _STATED:
                expected[column] = _stated_value(row[index])
            stated_data = _stated_value(row[_SOURCE_DATA])
            if offer["volume_source"] == "stated":
                expected["data_gb"] = stated_data
            elif stated_data is not None:
                problems.append(
                    f"{offer['offer_id']}: the source states the volume ({stated_data}), "
                    "so volume_source must be 'stated'"
                )
            for column, value in expected.items():
                actual = (
                    offer[column]
                    if column in ("family_ar", "name_ar", "price_lyd")
                    else _catalogue_value(offer, column)
                )
                if actual != value:
                    problems.append(
                        f"{offer['offer_id']}: {column} is {actual}, source says {value}"
                    )
    return problems


def validate_market(facts: dict) -> dict:
    """Return the facts, or raise InvalidCatalogueError if a table lacks a status or a source."""
    problems = []
    for name, table in facts.items():
        if not isinstance(table, dict):
            problems.append(f"- {name}: must be a table with a status and a source")
            continue
        if table.get("status") not in STATUSES:
            problems.append(f"- {name}: status must be one of {', '.join(STATUSES)}")
        if not table.get("source"):
            problems.append(f"- {name}: source is missing")
    if problems:
        raise InvalidCatalogueError(
            f"The Almadar market facts break their rules ({len(problems)} problems):\n"
            + "\n".join(problems)
        )
    return facts


def load_market(path: str | Path = MARKET_PATH) -> dict:
    with Path(path).open("rb") as f:
        return validate_market(tomllib.load(f))
