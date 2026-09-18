"""Privacy commitments, asserted rather than trusted.

Section 6.5: no raw MSISDN exists anywhere in this repository, and identifiers
are SHA-256 with salt.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from cvm.config import Settings
from cvm.ingest.hashing import MSISDN_PATTERN, hash_identifier

# Imported rather than re-spelled. A second, weaker copy of this regex is how
# the scan ends up passing on a number the real code would have caught -- and
# the earlier local copy did exactly that: it missed both the international
# spelling (trunk zero dropped) and the grouped one. Concretely, these two:
# +218912345678 and 091 234 5678  <- msisdn-fixture
MSISDN = re.compile(MSISDN_PATTERN.pattern.encode())

# The negative tests need a number that LOOKS real, so the scan would otherwise
# flag its own fixtures. A line carrying this marker is exempt -- which keeps
# the scan repository-wide instead of exempting a whole directory, and puts
# every exemption where a reviewer reads it.
FIXTURE_MARKER = b"msisdn-fixture"


def test_hash_is_64_hex_chars():
    digest = hash_identifier("0912345678")  # msisdn-fixture
    assert re.fullmatch(r"[0-9a-f]{64}", digest)


def test_hash_is_deterministic_for_a_given_salt():
    assert hash_identifier("0912345678") == hash_identifier("0912345678")  # msisdn-fixture


def test_different_salts_give_different_hashes():
    a = hash_identifier("0912345678", salt="a" * 64)  # msisdn-fixture
    b = hash_identifier("0912345678", salt="b" * 64)  # msisdn-fixture
    assert a != b


def test_placeholder_salt_is_rejected():
    """Shipping the .env.example placeholder must fail loudly."""
    with pytest.raises(ValueError, match="placeholder"):
        Settings(CVM_HASH_SALT="CHANGE_ME_generate_a_64_char_hex_string")


def test_missing_salt_raises_rather_than_defaulting():
    s = Settings(CVM_HASH_SALT="")
    with pytest.raises(RuntimeError, match="CVM_HASH_SALT"):
        s.require_salt()


def test_no_msisdn_pattern_in_tracked_python_sources():
    """The same check CI runs, so it fails on a laptop before it fails on a PR."""
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "*.py", "*.yaml", "*.yml", "*.json", "*.csv"],
            capture_output=True,
            check=True,
            text=True,
        ).stdout.split()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("not a git checkout, or git is unavailable")

    offenders = []
    for path in tracked:
        try:
            lines = Path(path).read_bytes().splitlines()
        except OSError:
            continue
        for lineno, line in enumerate(lines, start=1):
            if MSISDN.search(line) and FIXTURE_MARKER not in line:
                offenders.append(f"{path}:{lineno}")
    assert not offenders, f"Possible raw MSISDN in: {offenders}"


# --- The pattern itself ----------------------------------------------------
# The scan is only as good as its regex, so the regex is under test. Each of
# these is a real way a Libyan number is written.


@pytest.mark.parametrize(
    "raw",
    [
        "0912345678",  # msisdn-fixture  national, Libyana
        "0945551234",  # msisdn-fixture  national, Almadar
        "091 234 5678",  # msisdn-fixture  grouped
        "091-234-5678",  # msisdn-fixture  hyphenated
        "+218912345678",  # msisdn-fixture  international, trunk zero DROPPED
        "+218 91 234 5678",  # msisdn-fixture  international, grouped
        "218912345678",  # msisdn-fixture  no plus
        "+2180912345678",  # msisdn-fixture  international, trunk zero KEPT
    ],
)
def test_pattern_catches_every_real_spelling(raw: str):
    assert MSISDN_PATTERN.search(raw), f"{raw!r} would pass the privacy scan"


@pytest.mark.parametrize(
    "raw",
    [
        "0812345678",  # wrong prefix
        "0932345678",  # 093 is not allocated to either operator
        "09123456",  # too short
        "091234567890",  # msisdn-fixture: too long
        "912345678",  # no trunk zero and no country code: not phone-shaped
        "1234567890",
        "3.14159265",
    ],
)
def test_pattern_does_not_fire_on_other_numbers(raw: str):
    assert not MSISDN_PATTERN.search(raw)


def test_pattern_does_not_fire_inside_its_own_digests():
    """The false positive that matters most.

    A 64-char hex digest has a good chance of containing "094" followed by
    seven characters that happen to be digits. Without the lookarounds the scan
    reports a raw MSISDN in the one column guaranteed to be safe -- and whether
    it does depends on the salt, so it passes locally and fails in CI.
    """
    offenders = [
        d
        for salt in ("a" * 64, "b" * 64, "de2f0863" + "0" * 56)
        for d in (hash_identifier(str(i), salt) for i in range(400))
        if MSISDN_PATTERN.search(d)
    ]
    assert not offenders, f"{len(offenders)} digests matched, e.g. {offenders[0]}"
