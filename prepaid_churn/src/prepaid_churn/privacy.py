"""Pseudonymous identifiers and the raw phone number check (ticket T15, decision 17).

Ported by hand from `Ali_Branch`'s `src/cvm/ingest/hashing.py` at commit `06890f6`
(port log step 9 in `docs/ali_branch_merge.md`).
Ali's module hashed whole frames at the ingestion boundary and read its salt from a
settings object; this module keeps only the two things the service needs and takes the
salt as an argument, so every function here stays pure and testable.

The module has one job.
No raw Libyan mobile number may be accepted by the integration service, and an operator
who exports subscribers to us has one supported way to hide theirs before they do.
"""

import hashlib
import re

# The Libyan mobile prefixes 091, 092, 094 and 095, with or without a +218 country prefix.
# This is Ali's pattern, kept with all three of his corrections, because each one came
# from a real miss and the reasons still apply here:
#
# 1. The lookarounds keep the pattern out of the middle of a SHA-256 digest.
#    A 64-character hex string has a good chance of containing "094" followed by seven
#    more hex characters that happen to be digits, so a pattern without them reports a
#    raw number on the one value that is guaranteed to be safe.
# 2. The trunk zero is optional after a country code.
#    Libyan numbers are written 0912345678 nationally and +218912345678 internationally,
#    and a billing export uses the second form.
# 3. The digits are usually grouped, as in "091 234 5678" or "091-234-5678", so allowing
#    one separator in one fixed position misses both common groupings.
#
# A prefix stays required, either 218 or a trunk zero.
# Without it every nine-digit account number beginning 91, 92, 94 or 95 would match, and
# an account number is not a phone number.
MSISDN_PATTERN = re.compile(
    r"(?<![0-9a-zA-Z])"  # not inside a longer alphanumeric token
    r"(?:\+?218[ -]?(?:0[ -]?)?|0[ -]?)"  # +218 or 218 with an optional trunk 0, or a bare 0
    r"9[1245]"  # the Libyan mobile prefixes 91, 92, 94 and 95
    r"(?:[ -]?[0-9]){7}"  # seven more digits, however they are grouped
    r"(?![0-9])"
)

# The shortest salt worth having: a nine-digit number space is small enough that a short
# salt is brute-forced alongside the number itself.
MIN_SALT_LENGTH = 16


def looks_like_phone_number(value: object) -> bool:
    """True when the text holds something shaped like a Libyan mobile number."""
    return MSISDN_PATTERN.search(str(value)) is not None


def pseudonymize(raw: object, salt: str) -> str:
    """Salted SHA-256 of one raw identifier, for an operator to run before exporting.

    The salt is required rather than defaulted, and has a minimum length.
    An unsalted digest of a nine-digit number is reversed by hashing every number in the
    range, so it would pseudonymize nothing while looking like it had.
    """
    if len(salt) < MIN_SALT_LENGTH:
        raise ValueError(
            f"The salt must be at least {MIN_SALT_LENGTH} characters. "
            "An unsalted or short hash of a phone number can be reversed by trying "
            "every number, so it is not a pseudonym."
        )
    return hashlib.sha256(f"{salt}{raw}".encode()).hexdigest()
