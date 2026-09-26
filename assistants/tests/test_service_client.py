from pathlib import Path

import assistants.service_client as copy

ORIGINAL = Path(__file__).parents[2] / "prepaid_churn" / "src" / "prepaid_churn" / "client.py"


def _body(text: str) -> str:
    return text.replace("\r\n", "\n")


def test_the_copy_matches_the_prepaid_client():
    """Decision 25: copied, not imported, and a copy that drifts is caught here."""
    copied = _body(Path(copy.__file__).read_text(encoding="utf-8"))
    original = _body(ORIGINAL.read_text(encoding="utf-8"))
    header, separator, rest = copied.partition('"""')
    assert header.startswith("# Copied verbatim from prepaid_churn")
    assert separator + rest == original
