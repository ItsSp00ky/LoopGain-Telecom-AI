"""Shared loaders and helpers for both Streamlit apps.  Owner: E5

EVERY SCREEN READS WHAT THE PIPELINE WROTE. Nothing here recomputes a score, a
CLV or an offer -- a dashboard that recomputes is a dashboard that will
eventually disagree with the API, and the number an evaluator sees on screen
has to be the number the engine produced.

Caching is per-file with `@st.cache_data`, so a screen that needs the whole
base pays for it once per session rather than once per widget interaction.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from cvm.config import settings

# Streamlit reruns the whole script on every interaction, so anything touching
# disk is cached. One hour is longer than any demo and short enough that a
# re-run of the pipeline shows up without restarting the app.
TTL = 3600


def missing_banner(paths: dict[str, Path]) -> bool:
    """Name what is missing and which command produces it.

    A screen that renders empty charts with no explanation is worse than one
    that says "run phase 5". During a demo the second is recoverable.
    """
    absent = {name: path for name, path in paths.items() if not path.exists()}
    if not absent:
        return False
    st.error(
        "**This screen needs outputs that do not exist yet.**\n\n"
        + "\n".join(f"- `{name}` — missing `{path.name}`" for name, path in absent.items())
        + "\n\nRun the pipeline: `python -m cvm.features.run`, then the model phases.",
        icon=":material/error:",
    )
    return True


@st.cache_data(ttl=TTL)
def base() -> pd.DataFrame:
    """The latest snapshot per subscriber, with every model output joined."""
    frame = pd.read_parquet(settings.feature_store_offline)
    latest = (
        frame.sort_values("snapshot_date")
        .drop_duplicates(subset=["subscriber_id_hashed"], keep="last")
        .reset_index(drop=True)
    )

    scores = settings.processed_dir / "m1_scores.parquet"
    if scores.exists():
        latest = latest.merge(pd.read_parquet(scores), on="subscriber_id_hashed", how="left")

    clv = settings.processed_dir / "m2_clv.parquet"
    if clv.exists():
        value = pd.read_parquet(clv)
        latest["clv_12m"] = value["clv_12m"].to_numpy()
        latest["retention_ceiling_lyd"] = value["retention_ceiling_lyd"].to_numpy()

    uplift = settings.processed_dir / "m3_uplift.parquet"
    if uplift.exists():
        latest = latest.merge(
            pd.read_parquet(uplift).drop(
                columns=["clv_12m", "retention_ceiling_lyd"], errors="ignore"
            ),
            on="subscriber_id_hashed",
            how="left",
        )

    latest["tier"] = latest["tenure_months"].map(tier_of)
    return latest


@st.cache_data(ttl=TTL)
def report(name: str) -> dict | pd.DataFrame | None:
    """One written report from artifacts/reports, or None."""
    path = settings.reports_dir / name
    if not path.exists():
        return None
    if path.suffix == ".json":
        return json.loads(path.read_text())
    return pd.read_csv(path)


def tier_of(tenure_months) -> str:
    """Loyalty tier from tenure, per conf/pricing.yaml#tiers.

    Duplicated from the API rather than imported because the dashboard must
    keep rendering when the API is down, and because importing a FastAPI
    dependency into Streamlit drags the whole app object in. If the bands move
    in config, both read the same config.
    """
    tenure = 0.0 if pd.isna(tenure_months) else float(tenure_months)
    if tenure >= 84:
        return "platinum"
    if tenure >= 36:
        return "gold"
    if tenure >= 12:
        return "silver"
    return "bronze"


def synthetic_notice() -> None:
    """The caveat that goes on every screen showing a number.

    Not a footnote. Every metric in this dashboard comes from generated data,
    and an evaluator who leaves thinking otherwise has been misled by us rather
    than by the numbers.
    """
    st.caption(
        ":material/info: Every figure here is computed from **generated** data. "
        "Synthetic metrics are not evidence of production performance. The uplift "
        "model is validated separately on Criteo's real randomised arms — see the "
        "technical report for the real-data validation path."
    )


# --- Arabic -----------------------------------------------------------------
#
# Streamlit renders Arabic correctly in markdown when the direction is set, so
# the reshaper is only needed where text is drawn into an image or a monospace
# block that will not honour `dir`. The SMS preview is exactly that case.


def rtl(text: str) -> str:
    """Wrap Arabic in a right-to-left block."""
    return f"<div dir='rtl' style='text-align:right; font-size:1.05rem'>{text}</div>"


def shaped(text: str) -> str:
    """Reshape and bidi-order Arabic for a context that will not do it itself.

    Needed for the SMS handset preview, which is drawn in a fixed-width box:
    without reshaping, Arabic letters render in their isolated forms and the
    string reads as disconnected glyphs in the wrong order.
    """
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display

        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        # A missing optional dependency must not blank the screen mid-demo.
        return text


# --- SMS --------------------------------------------------------------------

# THE REAL LIMIT IS 70, NOT 160. GSM-7 gives 160 characters per part, but any
# Arabic character forces the whole message into UCS-2, where one part is 70
# characters. A preview that shows 160 would tell a campaign manager a message
# fits in one SMS when it will actually send as three, and they are billed per
# part.
GSM7_LIMIT = 160
UCS2_LIMIT = 70
UCS2_CONCAT_LIMIT = 67  # multi-part messages spend 6 bytes on the UDH header


def sms_parts(text: str) -> dict[str, object]:
    """How this message will actually be sent, and billed."""
    # Any character outside the GSM-7 basic set forces UCS-2 for the WHOLE
    # message -- one Arabic letter in an otherwise Latin string costs 90
    # characters of capacity.
    gsm7_basic = set(
        "@£$¥èéùìòÇØøÅåΔ_ΦΓΛΩΠΨΣΘΞÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
        "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà\n\r"
    )
    unicode_needed = any(character not in gsm7_basic for character in text)

    if not unicode_needed:
        limit, concat = GSM7_LIMIT, 153
        encoding = "GSM-7"
    else:
        limit, concat = UCS2_LIMIT, UCS2_CONCAT_LIMIT
        encoding = "UCS-2"

    length = len(text)
    parts = 1 if length <= limit else -(-length // concat)
    return {
        "encoding": encoding,
        "length": length,
        "limit": limit,
        "parts": parts,
        "remaining": (limit if parts == 1 else concat * parts) - length,
        "over_one_part": parts > 1,
    }
