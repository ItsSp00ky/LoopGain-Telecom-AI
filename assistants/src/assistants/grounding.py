"""The number check: an assistant may only say a number that a tool returned or the user said.

"Never invent a number" is rule 2 of `prepaid_churn/docs/integration.md` section 6.
A system prompt asks for it; this module enforces it, so a reply that quotes a price, a
volume or a rate from nowhere is discarded before anyone reads it.
"""

import re
from decimal import Decimal, InvalidOperation

# Arabic-Indic and Extended Arabic-Indic digits, and the Arabic decimal and thousands marks.
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬", "01234567890123456789.,")

# A thousands comma is followed by exactly three digits; any other comma is a decimal one.
_THOUSANDS = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")

# "1. " or "2) " at the start of a line numbers a list; it is not a figure.
_LIST_MARKER = re.compile(r"(?m)^\s*\d+[.)]\s+")


def _canonical(token: str) -> str:
    """One spelling per value, so "5", "5.0" and "5.00" are the same number."""
    try:
        value = Decimal(token.replace(",", "."))
    except InvalidOperation:
        return token
    if value == value.to_integral_value():
        return str(value.quantize(Decimal(1)))
    return format(value.normalize(), "f")


def numbers(text: str) -> set[str]:
    """Every number written in `text`, in canonical form."""
    text = _THOUSANDS.sub("", text.translate(_DIGITS))
    return {_canonical(token) for token in _NUMBER.findall(text)}


# Rule 5: never show a raw phone number, even one the user typed. The pattern is the prepaid
# service's own (`prepaid_churn/src/prepaid_churn/privacy.py`, where each part is explained):
# +218 or a trunk zero, then 91, 92, 94 or 95, then seven digits however they are grouped.
PHONE_NUMBER = re.compile(
    r"(?<![0-9a-zA-Z])(?:\+?218[ -]?(?:0[ -]?)?|0[ -]?)9[1245](?:[ -]?[0-9]){7}(?![0-9])"
)


def has_phone_number(text: str) -> bool:
    return PHONE_NUMBER.search(text.translate(_DIGITS)) is not None


def ungrounded(reply: str, sources: list[str]) -> set[str]:
    """The numbers in `reply` that none of `sources` contains."""
    allowed = set().union(*(numbers(source) for source in sources)) if sources else set()
    return numbers(_LIST_MARKER.sub("", reply.translate(_DIGITS))) - allowed
