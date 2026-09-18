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
from cvm.ingest.hashing import hash_identifier

# Libyana 091/092, Almadar 094/095, optionally prefixed +218.
MSISDN = re.compile(rb"(\+?218[ -]?)?(09[1245])[ -]?[0-9]{7}")

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
