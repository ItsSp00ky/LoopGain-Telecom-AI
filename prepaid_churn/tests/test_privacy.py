import pytest

from prepaid_churn.privacy import (
    MIN_SALT_LENGTH,
    looks_like_phone_number,
    pseudonymize,
)

SALT = "a-salt-long-enough-to-use"


@pytest.mark.parametrize(
    "number",
    [
        "0912345678",  # Libyana, written nationally
        "0945678901",  # Almadar
        "+218912345678",  # international, no trunk zero
        "218912345678",
        "+2180912345678",  # international with the trunk zero kept
        "091 234 5678",  # grouped with spaces
        "091-234-5678",  # grouped with dashes
        "call me on 0912345678 please",  # inside a longer text
    ],
)
def test_a_libyan_mobile_number_is_recognised(number):
    assert looks_like_phone_number(number)


@pytest.mark.parametrize(
    "value",
    [
        "0001",
        "69999",
        pseudonymize("0912345678", SALT),  # our own output must never look raw
        "912345678",  # nine digits with no prefix is an account number, not a number
        "0812345678",  # 081 is not a Libyan mobile prefix
        "09123456",  # too short
        "",
    ],
)
def test_an_identifier_that_is_not_a_phone_number_is_left_alone(value):
    assert not looks_like_phone_number(value)


def test_every_digest_of_a_real_number_stays_clear_of_the_pattern():
    """The lookarounds exist because a digest can contain "094" and seven digits.

    One example proves nothing here, so this walks a range of salts.
    """
    digests = [pseudonymize("0912345678", f"{SALT}-{n:04d}") for n in range(500)]
    assert not [digest for digest in digests if looks_like_phone_number(digest)]


def test_pseudonymize_is_stable_and_salted():
    assert pseudonymize("0912345678", SALT) == pseudonymize("0912345678", SALT)
    assert pseudonymize("0912345678", SALT) != pseudonymize("0912345679", SALT)
    assert pseudonymize("0912345678", SALT) != pseudonymize("0912345678", SALT + "x")
    assert len(pseudonymize("0912345678", SALT)) == 64


def test_a_missing_or_short_salt_is_refused():
    for salt in ("", "short", "x" * (MIN_SALT_LENGTH - 1)):
        with pytest.raises(ValueError, match="salt"):
            pseudonymize("0912345678", salt)
