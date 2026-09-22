"""Shared helpers for the demo screens (ticket T14).

Every screen reads what the pipeline wrote, through `prepaid_churn.demo`.
Nothing in `app/` computes a score, a tier, an offer or a threshold: a screen that
recomputes is a screen that will eventually disagree with the T15 service, and the number
an evaluator sees has to be the number the engine produced.
"""

import streamlit as st

from prepaid_churn.demo import DemoPaths, load_demo

CAPTION = "Team Loop Gain - Samsung Innovation Campus - Almadar Aljadid prepaid customers"


def configure(title: str, icon: str = "signal_cellular_alt") -> None:
    st.set_page_config(page_title=f"{title} - Loop Gain", page_icon=icon, layout="wide")


@st.cache_resource
def state():
    """Load every output once per session.

    `cache_resource` rather than `cache_data` because the state holds a loaded model
    bundle, which is shared rather than copied per caller.
    """
    return load_demo(DemoPaths.from_environment())


def refresh() -> None:
    """Drop the cache after a review, so the screens show the new status."""
    state.clear()


def missing_banner(demo, needed: tuple[str, ...]) -> bool:
    """Name what this screen is missing and the command that produces it."""
    absent = [(what, how) for what, how in demo.missing if what in needed]
    if not absent:
        return False
    st.error(
        "**This screen needs outputs that do not exist yet.**\n\n"
        + "\n".join(f"- `{what}` - produced by `{how}`" for what, how in absent),
        icon=":material/error:",
    )
    return True


def degraded_notice(demo) -> None:
    """The caveat that belongs on every screen showing a number.

    This checkout has no gated churn bundle, so risk-based figures are unavailable rather
    than zero. An evaluator who leaves thinking otherwise was misled by us.
    """
    if demo.has_risk:
        return
    st.warning(
        "**No gated churn bundle in this checkout.** Risk and risk-based value are "
        "**unavailable**, not zero. Tiers, spend and the catalogue are real; every figure "
        "that needs a churn probability is blank on purpose. Run `uv run churn bundle` "
        "and `uv run churn tiers` to fill them.",
        icon=":material/info:",
    )


def rtl(text: str) -> str:
    """Wrap Arabic so the browser lays it out right to left."""
    return (
        f"<div dir='rtl' lang='ar' style='text-align:right; font-size:1.05rem; "
        f"line-height:1.9'>{text}</div>"
    )


def lyd(value, digits: int = 0) -> str:
    """Money, or an explicit dash when the figure is unavailable."""
    if value is None:
        return "-"
    return f"{float(value):,.{digits}f} LYD"


def expected(value) -> str:
    """A fractional expectation, keeping a decimal while it is small.

    0.7 expected churners is not 1. Rounding it to a whole number reads as certainty, and
    it only shows up on a base small enough for the fraction to matter, which is exactly
    the single-customer case this app is meant to be opened on.
    """
    if value is None:
        return "-"
    value = float(value)
    return f"{value:,.1f}" if value < 10 else f"{value:,.0f}"


def ordered_bar(
    frame,
    order,
    label: str = "group",
    value: str = "customers",
    horizontal: bool = False,
    height: int = 260,
):
    """A bar chart in the order the categories mean, not alphabetical.

    `st.bar_chart` sorts its axis alphabetically, which put the value tiers on screen as
    high, low, medium, very_high, very_low: an ordering that says nothing, right next to a
    table that was correctly ordered. Only visible by opening the page.
    Altair ships with Streamlit, so an explicit sort costs no new dependency.
    """
    import altair as alt

    category = alt.Y if horizontal else alt.X
    measure = alt.X if horizontal else alt.Y
    # Customers are whole people, so the axis never shows 0.05 of one. Altair defaults to
    # fine fractional ticks when every bar is 1, which is what a small campaign looks like.
    ticks = alt.Axis(format="d", tickMinStep=1)
    # labelLimit=0 keeps the whole category name. The guardrail reasons are sentences, and
    # Altair's default truncated them to "No offer: low chu..." on the real campaign.
    names = alt.Axis(labelLimit=0)
    axes = {
        "y" if horizontal else "x": category(
            f"{label}:N", sort=list(order), title=None, axis=names
        ),
        "x" if horizontal else "y": measure(
            f"{value}:Q", title=value.replace("_", " "), axis=ticks
        ),
    }
    return (
        alt.Chart(frame)
        .mark_bar()
        .encode(**axes, tooltip=[alt.Tooltip(name) for name in frame.columns])
        .properties(height=height)
    )
