"""Identifier hashing. The single place a raw identifier may be touched.

No raw MSISDN exists anywhere in this repository. That commitment is only
credible if there is exactly one function that does the hashing and it is
impossible to bypass -- so every loader routes through here, and the salt is
required rather than defaulted.
"""

from __future__ import annotations

import hashlib
import re

import pandas as pd

from cvm.config import settings

# Libyana 091/092, Almadar 094/095, with or without a +218 country prefix.
# Same pattern as the CI job and tests/unit/test_privacy.py -- three copies of
# one regex is two too many, so this is the one the code uses and the others
# exist to catch the case where this module is bypassed entirely.
#
# Two corrections over the naive spelling, both found by testing it:
#
# 1. THE LOOKAROUNDS. Without them the pattern matches INSIDE a SHA-256 digest:
#    a 64-char hex string has a good chance of containing "094" followed by
#    seven more characters that happen to be digits. Scanning our own hashed
#    output would then report a raw MSISDN -- a false positive on the one
#    column guaranteed to be safe, firing unpredictably depending on the salt.
#
# 2. THE LEADING ZERO IS OPTIONAL AFTER A COUNTRY CODE. Libyan numbers are
#    written nationally with a trunk zero and internationally without it, so a
#    pattern requiring "09" after the 218 misses every number written the
#    international way -- which is the way they arrive in a billing export.
#    Examples: 0912345678 versus +218912345678.     <- msisdn-fixture
#
# 3. THE DIGITS ARE OFTEN GROUPED. Nobody writes a number unbroken on a form;
#    they group it. A pattern allowing one separator in one fixed position
#    misses both common groupings.
#    Examples: 091 234 5678 and 091-234-5678.       <- msisdn-fixture
#
# A prefix is REQUIRED -- either 218 or a trunk zero. Dropping that would make
# any nine-digit number beginning 91/92/94/95 a match, and an account number is
# not a phone number.
MSISDN_PATTERN = re.compile(
    r"(?<![0-9a-zA-Z])"  # not inside a longer alphanumeric token
    r"(?:\+?218[ -]?(?:0[ -]?)?|0[ -]?)"  # +218 / 218 (+ optional trunk 0), or a bare 0
    r"9[1245]"  # Libyana 91/92, Almadar 94/95
    r"(?:[ -]?[0-9]){7}"  # seven more digits, however they are grouped
    r"(?![0-9])"
)

# A column of 64-char lowercase hex is already hashed; re-hashing it would
# produce a digest nothing else can join to.
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


def hash_identifier(raw: str, salt: str | None = None) -> str:
    """Return the salted SHA-256 hex digest of one raw identifier.

    Raises if no salt is configured: an unsalted hash is trivially reversible
    for a 9-digit number space and cannot be reconciled across runs.
    """
    salt = salt or settings.require_salt()
    return hashlib.sha256(f"{salt}{raw}".encode()).hexdigest()


def hash_column(
    df: pd.DataFrame,
    source_column: str,
    target_column: str = "subscriber_id_hashed",
    drop_source: bool = True,
) -> pd.DataFrame:
    """Hash an identifier column and drop the original.

    ``drop_source`` defaults to True on purpose. Keeping the raw column "just
    for debugging" is how it ends up in a Parquet file and then in a commit.
    """
    if source_column not in df.columns:
        raise KeyError(f"{source_column!r} not in frame. Columns: {sorted(df.columns)[:12]}...")

    out = df.copy()
    raw = out[source_column].astype("string")

    if raw.isna().any():
        n = int(raw.isna().sum())
        raise ValueError(
            f"{source_column!r} has {n} null identifiers. A subscriber with no id "
            "cannot be joined to anything downstream, so this is a data problem "
            "to resolve at the source rather than a row to hash as 'None'."
        )

    # Resolve the salt once. Per-row lookup would re-read settings 100,000
    # times, and a salt that changed mid-frame would be silently catastrophic.
    salt = settings.require_salt()

    already = raw.str.fullmatch(_DIGEST)
    if bool(already.all()):
        # Idempotent: re-running ingestion on landed data must not double-hash.
        out[target_column] = raw
    elif bool(already.any()):
        raise ValueError(
            f"{source_column!r} mixes raw identifiers with 64-char digests "
            f"({int(already.sum())} of {len(already)} already hashed). Hashing this "
            "column would produce two id spaces that cannot be joined."
        )
    else:
        out[target_column] = raw.map(lambda v: hash_identifier(v, salt)).astype("string")

    if drop_source and source_column != target_column:
        out = out.drop(columns=[source_column])

    assert_no_raw_identifiers(out)
    return out


def assert_no_raw_identifiers(df: pd.DataFrame) -> None:
    """Fail if any column looks like it holds a raw Libyan MSISDN.

    Pattern: optional +218, then 091/092 (Libyana) or 094/095 (Almadar),
    then 7 digits. Called at the end of every loader and asserted in
    tests/unit/test_privacy.py.

    Checks values AND column names: a column literally called `msisdn` is a
    problem even when this particular sample happens not to match the pattern.
    """
    offenders: list[str] = []

    for name in df.columns:
        if any(t in str(name).lower() for t in ("msisdn", "phone_number", "mobile_number")):
            offenders.append(f"column name {name!r}")

    for name in df.columns:
        col = df[name]
        if col.dtype.kind not in {"O", "U", "S"} and str(col.dtype) != "string":
            # Numeric columns cannot carry a +218 prefix or a leading zero, so
            # a raw MSISDN would have to arrive as text to survive this far.
            continue
        sample = col.dropna().astype(str)
        if sample.empty:
            continue
        # A column that is entirely 64-char digests is this module's own output.
        # Skipping it outright is belt-and-braces alongside the lookarounds in
        # MSISDN_PATTERN: a digest could in principle *begin* with ten matching
        # characters, where a lookbehind has nothing to bite on.
        if bool(sample.str.fullmatch(_DIGEST).all()):
            continue
        if sample.str.contains(MSISDN_PATTERN, regex=True, na=False).any():
            offenders.append(f"values in {name!r}")

    if offenders:
        raise ValueError(
            "Possible raw MSISDN found: "
            + ", ".join(offenders)
            + ". Hash at the ingestion boundary with hash_column(); no raw "
            "identifier may reach data/interim or data/processed."
        )
