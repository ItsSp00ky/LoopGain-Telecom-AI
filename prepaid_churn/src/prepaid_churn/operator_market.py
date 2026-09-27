"""The operator's packages and market facts (ticket T16, decisions 16 and 45).

`data/operator/offers.csv` lists what the operator sells, one row per package.
It is curated from the operator's own file in `data/operator/source/`, and
`check_against_source` proves that every price, volume, minute count, member count
and speed the operator states still matches that file.
`data/operator/market.toml` holds every other fact a calculation needs, each with a
status and a source. `docs/operator.md` explains both files.

`operator_view` (ticket T18) shows each real customer in the operator's terms: monthly spend
in LYD, the usual recharge card and the operator's bundle the customer would hold. It
reads only the two feature months of a window and never changes a churn feature.
`unconverted_behaviour` measures what that conversion cannot carry over from the source
market, so the report can say it.
"""

import csv
import re
import tomllib
from pathlib import Path

import numpy as np
import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaErrors

from prepaid_churn.data import PROJECT_ROOT
from prepaid_churn.schema import ID, summarize_failures
from prepaid_churn.windows import Window, window_features

OPERATOR_DIR = PROJECT_ROOT / "data" / "operator"
OFFERS_PATH = OPERATOR_DIR / "offers.csv"
EXCLUDED_PATH = OPERATOR_DIR / "excluded.csv"
MARKET_PATH = OPERATOR_DIR / "market.toml"

OPERATORS = ("Libyan mobile operator",)
# Where a package's data volume comes from: the operator file states it, it is read from
# the package name ("نت 20" is 20 GB), a teammate reported it, or nobody knows it.
VOLUME_SOURCES = ("stated", "name", "reported", "none")
STATUSES = ("confirmed", "measured", "reported", "assumption", "estimate")

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
            summarize_failures(errors.failure_cases, "The operator catalogue breaks its rules")
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


EXCLUDED_COLUMNS = (
    "offer_id",
    "family_en",
    "source_file",
    "source_row",
    "reason",
    "decided_by",
    "decided_on",
)


def load_excluded(path: str | Path = EXCLUDED_PATH) -> pd.DataFrame:
    """Operator rows deliberately left out of the catalogue, each with a reason.

    A package the operator no longer sells has to leave the catalogue, but it must not
    simply vanish: the source files are byte-for-byte copies of the operator's own export,
    and `check_against_source` requires every row in them to be accounted for.
    Recording the removal here keeps that guarantee, so a package cannot be dropped
    silently, which is exactly how the Mix families went missing in the first place.
    """
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=list(EXCLUDED_COLUMNS))
    excluded = pd.read_csv(path)
    missing = set(EXCLUDED_COLUMNS) - set(excluded.columns)
    if missing:
        raise InvalidCatalogueError(f"{path.name} is missing columns: {sorted(missing)}")
    blank = [
        column for column in ("reason", "decided_by", "decided_on") if excluded[column].isna().any()
    ]
    if blank:
        raise InvalidCatalogueError(
            f"Every excluded package needs a reason, a name and a date; {blank} has blanks."
        )
    return excluded


def check_against_source(
    offers: pd.DataFrame,
    directory: str | Path = OPERATOR_DIR,
    excluded: pd.DataFrame | None = None,
) -> list[str]:
    """Problems where the catalogue no longer matches the operator's own file.

    Checks that every source row is either in the catalogue exactly once or recorded in
    `excluded.csv` with a reason, and that the family, name, price and every value the
    operator states (volume, minutes, speeds, members) match.
    A volume the file states must be marked "stated"; volumes it leaves out (read from
    the name or reported by a teammate) cannot be compared.
    """
    problems = []
    excluded = load_excluded() if excluded is None else excluded
    for source_file, rows in offers.groupby("source_file"):
        with (Path(directory) / source_file).open(encoding="utf-8-sig", newline="") as f:
            source = list(csv.reader(f))[1:]
        counts = rows["source_row"].value_counts()
        dropped = set(excluded.loc[excluded["source_file"].eq(source_file), "source_row"])
        source_rows = set(range(1, len(source) + 1))
        if overlap := sorted(dropped & set(counts.index)):
            problems.append(
                f"{source_file}: source rows {overlap} are both in the catalogue and "
                "recorded as excluded"
            )
        missing = sorted(source_rows - dropped - set(counts.index))
        repeated = sorted(counts[counts > 1].index)
        # "Unknown" means the row is not in the operator's file at all, which an excluded
        # row still is; a row in both places is reported once, by the message above.
        unknown = sorted(set(counts.index) - source_rows)
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
    for name, field in (("arpu", "monthly_lyd"), ("reference_spend", "mean_monthly_recharge")):
        table = facts.get(name, {})
        if not isinstance(table, dict) or not _positive_number(table.get(field)):
            problems.append(f"- {name}.{field}: must be a finite positive number")
    cards = facts.get("recharge_cards", {})
    if not isinstance(cards, dict) or not _valid_cards(cards.get("values_lyd")):
        problems.append("- recharge_cards.values_lyd: must be a non-empty list of positive cards")
    if problems:
        raise InvalidCatalogueError(
            f"The operator market facts break their rules ({len(problems)} problems):\n"
            + "\n".join(problems)
        )
    return facts


def _positive_number(value) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and np.isfinite(value)
        and value > 0
    )


def _valid_cards(cards) -> bool:
    return isinstance(cards, list) and bool(cards) and all(_positive_number(card) for card in cards)


def load_market(path: str | Path = MARKET_PATH) -> dict:
    with Path(path).open("rb") as f:
        return validate_market(tomllib.load(f))


# --- T18: the real customers in the operator's terms (decision 16) -------------------------

PAY_AS_YOU_GO = "PAYG"
MONTHLY_FAMILY = "Monthly offers"
DAILY_FAMILY = "Daily offers"
WEEKLY_FAMILY = "Weekly offers"
# The source data's short packs are "service schemes with validity smaller than a month",
# so the operator's weekly packs are as much their match as its daily ones (decision 48).
SHORT_FAMILIES = (DAILY_FAMILY, WEEKLY_FAMILY)
VIEW_COLUMNS = (ID, "monthly_spend_lyd", "usual_card_lyd", "bundle_held", "bundle_price_lyd")


def lyd_rate(market: dict) -> float:
    """LYD per unit of the source currency, so the reference customer spends the operator's ARPU."""
    validate_market(market)
    return market["arpu"]["monthly_lyd"] / market["reference_spend"]["mean_monthly_recharge"]


def _recharge(frame: pd.DataFrame, prefix: str) -> pd.Series:
    """Airtime plus data recharge in one window month (the value definition of T4)."""
    data = frame[f"{prefix}_total_rech_data"] * frame[f"{prefix}_av_rech_amt_data"]
    return frame[f"{prefix}_total_rech_amt"] + data


def _monthly_spend(frame: pd.DataFrame, rate: float) -> pd.Series:
    """Average airtime plus data recharge of the two window months, in LYD."""
    return (_recharge(frame, "prev") + _recharge(frame, "cur")) / 2 * rate


def _usual_topup(frame: pd.DataFrame, rate: float) -> pd.Series:
    """Average airtime top-up of the two window months, in LYD; empty without a top-up."""
    recharges = frame["prev_total_rech_num"] + frame["cur_total_rech_num"]
    airtime = frame["prev_total_rech_amt"] + frame["cur_total_rech_amt"]
    return (airtime / recharges.where(recharges > 0)) * rate


def nearest_card(amount_lyd: pd.Series, cards: list[float]) -> pd.Series:
    """The recharge card closest to each amount (the smaller card on a tie); empty stays empty."""
    if not _valid_cards(cards):
        raise InvalidCatalogueError(
            "The recharge cards must be a non-empty list of positive values."
        )
    cards = np.sort(np.asarray(cards, dtype=float))
    values = amount_lyd.to_numpy(dtype=float)
    nearest = cards[np.abs(values[:, None] - cards[None, :]).argmin(axis=1)]
    return pd.Series(np.where(np.isnan(values), np.nan, nearest), index=amount_lyd.index)


def _package_for(amount_lyd: pd.Series, family: pd.DataFrame) -> np.ndarray:
    """The dearest package of a family the amount pays for, or the cheapest one if none."""
    if family.empty:
        raise InvalidCatalogueError(
            "The operator view needs a monthly offer family and a daily or weekly one."
        )
    family = family.sort_values("price_lyd")
    position = np.searchsorted(family["price_lyd"].to_numpy(), amount_lyd.to_numpy(), "right")
    return family["offer_id"].to_numpy()[np.clip(position - 1, 0, len(family) - 1)]


def bundle_held(frame: pd.DataFrame, rate: float, offers: pd.DataFrame) -> pd.Series:
    """The operator data bundle matching each customer's packs in the current month.

    A monthly pack buyer gets the dearest operator monthly bundle their data spend pays
    for; a buyer of short packs only gets the dearest daily or weekly pack their average
    data recharge pays for; everybody else is on pay-as-you-go.
    Until decision 48 short packs were matched to daily packs only, which capped three in
    four of these customers at the 3 LYD pack whatever they spent on each top-up.
    """
    monthly_packs = frame["cur_monthly_2g"] + frame["cur_monthly_3g"]
    short_packs = frame["cur_sachet_2g"] + frame["cur_sachet_3g"]
    average_data = frame["cur_av_rech_amt_data"] * rate
    data_spend = frame["cur_total_rech_data"] * average_data
    monthly = _package_for(data_spend, offers[offers["family_en"] == MONTHLY_FAMILY])
    short = _package_for(average_data, offers[offers["family_en"].isin(SHORT_FAMILIES)])
    held = np.where(monthly_packs > 0, monthly, np.where(short_packs > 0, short, PAY_AS_YOU_GO))
    return pd.Series(held, index=frame.index, dtype="str")


def operator_view(
    cleaned: pd.DataFrame, window: Window, market: dict, offers: pd.DataFrame
) -> pd.DataFrame:
    """One row per customer: spend in LYD, usual recharge card and the bundle held."""
    frame = window_features(cleaned, window)
    rate = lyd_rate(market)
    usual = _usual_topup(frame, rate)
    held = bundle_held(frame, rate, offers)
    prices = offers.set_index("offer_id")["price_lyd"]
    return pd.DataFrame(
        {
            ID: cleaned[ID],
            "monthly_spend_lyd": _monthly_spend(frame, rate),
            "usual_card_lyd": nearest_card(usual, market["recharge_cards"]["values_lyd"]),
            "bundle_held": held,
            "bundle_price_lyd": held.map(prices).astype(float),
        }
    )


def unconverted_behaviour(frame: pd.DataFrame, market: dict, offers: pd.DataFrame) -> dict:
    """The habits the one rate cannot turn into the operator's market, measured.

    `frame` holds the window features of the customers described. The rate converts money,
    but how much data these customers use, how often they top up, how much each top-up is
    and how far the biggest spenders go stay the source market's. Measuring them lets the
    report say so, instead of a converted figure passing for one of the operator's.
    """
    rate = lyd_rate(market)
    data_mb = frame["cur_vol_2g_mb"] + frame["cur_vol_3g_mb"]
    usual = _usual_topup(frame, rate).dropna()
    spend = _monthly_spend(frame, rate)
    smallest = min(float(card) for card in market["recharge_cards"]["values_lyd"])
    dearest = float(offers["price_lyd"].max())
    above = spend > dearest
    total = float(spend.sum())
    return {
        "customers": len(frame),
        "no_data_share": float(data_mb.le(0).mean()),
        "median_data_gb": float(data_mb[data_mb > 0].median() / 1024),
        "median_topups_per_month": float(
            ((frame["prev_total_rech_num"] + frame["cur_total_rech_num"]) / 2).median()
        ),
        "smallest_card_lyd": smallest,
        "below_smallest_card_share": float(usual.lt(smallest).mean()),
        "dearest_package_lyd": dearest,
        "above_dearest_package": int(above.sum()),
        "above_dearest_spend_share": float(spend[above].sum() / total) if total > 0 else 0.0,
        "highest_spend_lyd": float(spend.max()),
    }


def _unconverted_lines(behaviour: dict) -> list[str]:
    """The report section for `unconverted_behaviour`; a value it could not measure is "-"."""

    def shown(value: float, template: str) -> str:
        return "-" if pd.isna(value) else template.format(value)

    b = behaviour
    above = b["above_dearest_package"]
    above_share = above / b["customers"] if b["customers"] else float("nan")
    return [
        "## What the rate does not convert",
        "",
        "The rate turns the source currency into LYD, but the habits below stay the source "
        "market's, so no figure built on them is one of the operator's.",
        "",
        "| Habit in this base | Value |",
        "|---|---|",
        f"| Customers who used no mobile data this month | {shown(b['no_data_share'], '{:.1%}')} |",
        f"| Median data used by the others | {shown(b['median_data_gb'], '{:.2f} GB a month')} |",
        f"| Median airtime top-ups | {shown(b['median_topups_per_month'], '{:g} a month')} |",
        f"| Customers whose average top-up converts to less than the smallest card "
        f"({b['smallest_card_lyd']:g} LYD) | "
        f"{shown(b['below_smallest_card_share'], '{:.1%} of those who recharged')} |",
        f"| Customers spending more a month than the dearest package "
        f"({b['dearest_package_lyd']:g} LYD) | {above} ({shown(above_share, '{:.1%}')}), with "
        f"{b['above_dearest_spend_share']:.1%} of all spend; the highest spends "
        f"{shown(b['highest_spend_lyd'], '{:,.0f}')} LYD |",
        "",
        "Nothing below the smallest card can be topped up at the operator (recharge cards "
        "above), so the usual card is the card such a customer would buy there, not one this "
        "data shows.",
        "",
    ]


def view_report(
    view: pd.DataFrame, active: pd.Series, market: dict, source: str, behaviour: dict
) -> str:
    """Markdown summary of the operator view of the active customers, with every assumption.

    `behaviour` is `unconverted_behaviour` for the same active customers.
    """
    from prepaid_churn.profile import markdown_table

    shown = view[active.to_numpy()]
    spend = shown["monthly_spend_lyd"]
    spread = pd.DataFrame(
        {
            "monthly spend (LYD)": {
                "mean": spend.mean(),
                "10th percentile": spend.quantile(0.10),
                "25th percentile": spend.quantile(0.25),
                "median": spend.median(),
                "75th percentile": spend.quantile(0.75),
                "90th percentile": spend.quantile(0.90),
            }
        }
    ).round(2)
    cards = (
        shown["usual_card_lyd"]
        .map(lambda card: "no recharge in the window" if pd.isna(card) else f"{card:.0f} LYD")
        .value_counts(normalize=True)
        .rename("share")
        .round(4)
        .to_frame()
    )
    bundles = (
        shown.groupby("bundle_held", dropna=False)
        .agg(customers=(ID, "size"), price_lyd=("bundle_price_lyd", "first"))
        .assign(share=lambda t: (t["customers"] / len(shown)).round(4))
        .sort_values("customers", ascending=False)
    )
    arpu, reference = market["arpu"], market["reference_spend"]
    return "\n".join(
        [
            "# T18 operator view of the real customers",
            "",
            f"Generated by `uv run churn operator-view` from `{source}`.",
            f"{len(shown)} customers active in the current month; {int((~active).sum())} already "
            "silent customers are left out, as in scoring (decision 12).",
            "The behaviour is real (upGrad prepaid data from another market); the money and the "
            "packages are the operator's (decision 16).",
            "",
            "## Assumptions",
            "",
            "| What | Value | Status | Source |",
            "|---|---|---|---|",
            f"| Operator ARPU | {arpu['monthly_lyd']:.0f} LYD per month | {arpu['status']} | "
            f"{arpu['source']} |",
            f"| Reference monthly recharge | {reference['mean_monthly_recharge']:.2f} in the "
            f"source currency | {reference['status']} | {reference['source']} |",
            f"| Rate | 1 unit of the source currency = {lyd_rate(market):.6f} LYD | derived | "
            "ARPU divided by the reference recharge |",
            f"| Recharge cards | {', '.join(map(str, market['recharge_cards']['values_lyd']))} LYD"
            f" | {market['recharge_cards']['status']} | {market['recharge_cards']['source']} |",
            "| Bundle held | monthly pack buyers get the dearest operator monthly bundle their "
            "data spend pays for; short-pack buyers get the dearest daily or weekly pack their "
            "average data recharge pays for (decision 48); everybody else is pay-as-you-go | "
            "assumption | T18 rule |",
            "",
            "Monthly spend is the average airtime plus data recharge of the two window months.",
            "The usual card is the operator's card nearest to the customer's average airtime "
            "recharge.",
            f"This base's mean spend is {spend.mean():.2f} LYD; it differs from the ARPU because "
            "the rate is fixed on the training customers, not on the viewed batch.",
            "",
            "## Monthly spend",
            "",
            markdown_table(spread, "statistic"),
            "",
            "## Usual recharge card",
            "",
            markdown_table(cards, "card"),
            "",
            "## Bundle held in the current month",
            "",
            markdown_table(bundles, "bundle"),
            "",
            *_unconverted_lines(behaviour),
        ]
    )
