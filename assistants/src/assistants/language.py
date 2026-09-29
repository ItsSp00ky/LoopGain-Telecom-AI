"""Which language a text is in, decided in code so neither the model nor the screen guesses."""

import re

_ARABIC_LETTER = re.compile(r"[؀-ۿ]")
_LATIN_LETTER = re.compile(r"[A-Za-z]")


def is_arabic(text: str) -> bool:
    """Any Arabic at all: a customer who writes one Arabic word is answered in Arabic."""
    return bool(_ARABIC_LETTER.search(text))


def mostly_arabic(text: str) -> bool:
    """More Arabic letters than Latin ones: how a reply should be laid out and checked."""
    return len(_ARABIC_LETTER.findall(text)) > len(_LATIN_LETTER.findall(text))
