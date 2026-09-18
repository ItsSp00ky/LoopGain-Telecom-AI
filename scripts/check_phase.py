"""Run the verification for one roadmap phase.

    python scripts/check_phase.py 0        # setup
    python scripts/check_phase.py 1        # ingestion
    python scripts/check_phase.py          # every phase that can run yet

ONE PORTABLE COMMAND PER PHASE, and that is the point. The checks in
docs/ROADMAP.md were originally inline `python -c "..."` one-liners, which do
not survive the trip between cmd.exe, PowerShell and bash: `cp` is not a
command on Windows, quoting rules differ three ways, and a multi-line -c string
cannot be typed into cmd.exe at all. A script has none of those problems.

Each check prints PASS, FAIL or PENDING. PENDING means the layer it tests is
not built yet -- expected, not a problem, and it names the phase that fixes it.
Exit code is non-zero only for a real FAIL, so this is safe to put in CI.
"""

from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

PASS, FAIL, PENDING = "PASS", "FAIL", "PEND"


# N818 wants an `Error` suffix, and this deliberately has none: a pending check
# is not an error. "Not built yet" is the expected state for eight of eleven
# phases, and calling it PendingError would report normal progress as failure.
class Pending(Exception):  # noqa: N818
    """Raised by a check whose layer is not implemented yet."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False
    )


def _needs(module: str, phase: str) -> object:
    """Import a module, or declare the phase that has to land first."""
    try:
        return importlib.import_module(module)
    except (ImportError, ModuleNotFoundError) as exc:
        raise Pending(f"{module} unavailable ({exc}); see phase {phase}") from exc


# ---------------------------------------------------------------------------
# Phase 0 -- setup
# ---------------------------------------------------------------------------


def check_salt() -> str:
    from cvm.config import settings

    salt = settings.require_salt()
    if len(salt) != 64:
        raise AssertionError(f"salt is {len(salt)} chars, expected 64")
    return f"present, starts {salt[:8]}"


def check_env_is_ignored() -> str:
    r = subprocess.run(
        ["git", "check-ignore", ".env"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if r.returncode != 0:
        raise AssertionError(".env is NOT gitignored -- it must never be committed")
    return "gitignored"


def check_python_version() -> str:
    major, minor = sys.version_info[:2]
    if (major, minor) != (3, 11):
        raise AssertionError(f"Python {major}.{minor}; the stack pins 3.11")
    return f"{major}.{minor}"


def check_packages() -> str:
    import importlib.metadata as md

    required = [
        "pandas",
        "duckdb",
        "polars",
        "pandera",
        "lightgbm",
        "lifelines",
        "lifetimes",
        "scikit-uplift",
        "shap",
        "pulp",
        "sdv",
        "fastapi",
        "streamlit",
        "mlflow",
        "openpyxl",
    ]
    missing = [p for p in required if not _installed(p, md)]
    if missing:
        raise AssertionError(f"missing: {missing}")
    return f"{len(required)} key packages present"


def _installed(name: str, md) -> bool:
    try:
        md.version(name)
        return True
    except Exception:
        return False


def check_tests() -> str:
    r = _run("-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider", "-o", "addopts=")
    tail = [ln for ln in r.stdout.splitlines() if "passed" in ln or "failed" in ln]
    if r.returncode != 0:
        raise AssertionError(tail[-1] if tail else "pytest failed")
    return tail[-1].strip() if tail else "passed"


def check_lint() -> str:
    ruff = _run("-m", "ruff", "check", "src", "tests", "apps", "scripts")
    if ruff.returncode != 0:
        raise AssertionError(f"ruff: {ruff.stdout.strip().splitlines()[-1]}")
    black = _run("-m", "black", "--check", "src", "tests", "apps", "scripts")
    if black.returncode != 0:
        raise AssertionError("black --check failed; run: python -m black src tests apps scripts")
    return "ruff + black clean"


def check_remote() -> str:
    r = subprocess.run(
        ["git", "remote", "-v"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if not r.stdout.strip():
        raise Pending("no git remote; see phase 0.3 -- nothing has been pushed anywhere")
    return r.stdout.splitlines()[0].split()[1]


# ---------------------------------------------------------------------------
# Phase 1 -- ingestion
# ---------------------------------------------------------------------------


def check_uci_duplicates() -> str:
    uci = _needs("cvm.ingest.uci_iranian", "1")
    from cvm.config import load_conf

    quality = load_conf("data")["sources"]["uci_iranian"]["quality"]
    audit = uci.duplicate_audit()
    dropped, expected = audit["duplicates_dropped"], quality["expected_duplicate_rows"]
    if abs(dropped - expected) > quality["duplicate_row_tolerance"]:
        raise AssertionError(f"dropped {dropped:.0f}, config expects ~{expected}")
    return (
        f"{dropped:.0f} dropped ({audit['duplicate_share']:.2%}), {audit['rows_clean']:.0f} clean"
    )


def check_uci_leaky_field() -> str:
    uci = _needs("cvm.ingest.uci_iranian", "1")
    from cvm.config import load_conf

    leaky = load_conf("data")["sources"]["uci_iranian"]["leaky_columns"]
    honest, naive = uci.load(), uci.load(drop_leaky=False)
    for column in leaky:
        if column in honest.columns:
            raise AssertionError(f"{column} reached the honest feature matrix")
        if column not in naive.columns:
            raise AssertionError(f"{column} missing from the naive reproduction")
    return f"{leaky} dropped from the honest path, kept in the naive one"


def check_cell2cell_join() -> str:
    c2c = _needs("cvm.ingest.cell2cell", "1")
    df = c2c.load()
    leaked = sorted(set(c2c.FORBIDDEN_COLUMNS) & set(df.columns))
    if leaked:
        raise AssertionError(f"protected columns survived: {leaked}")
    if not df["subscriber_id_hashed"].is_unique:
        raise AssertionError("hashed ids are not unique")
    return f"{len(df):,} rows, {len(c2c.FORBIDDEN_COLUMNS)} protected columns dropped"


def check_cell2cell_distributions() -> str:
    c2c = _needs("cvm.ingest.cell2cell", "1")
    # The figures quoted in the proposal and docs/data_dictionary.md.
    expected = {
        "incoming_outgoing_ratio": 0.280,
        "offpeak_data_ratio": 0.424,
        "usage_decay_ratio": 1.012,
        "revenue_decay_ratio": 1.000,
    }
    measured = c2c.measured_distributions()
    drifted = [
        f"{k} {measured[k]['median']:.3f} vs {v:.3f}"
        for k, v in expected.items()
        if abs(measured[k]["median"] - v) > 0.02
    ]
    if drifted:
        raise AssertionError("medians drifted from the documented figures: " + "; ".join(drifted))
    return "all four medians match the documented figures"


def check_ibm_protected_columns() -> str:
    ibm = _needs("cvm.ingest.ibm_telco", "1")
    df = ibm.load()
    leaked = sorted(set(ibm.FORBIDDEN_COLUMNS) & set(df.columns))
    if leaked:
        raise AssertionError(f"protected/geographic columns survived: {leaked}")
    return f"{len(df):,} rows, {len(ibm.FORBIDDEN_COLUMNS)} protected/geographic columns dropped"


def check_criteo_arms() -> str:
    criteo = _needs("cvm.ingest.criteo_uplift", "1")
    x, y, t = criteo.load(sample_10pct=True)
    leaked = [c for c in criteo.POST_TREATMENT_COLUMNS if c in x.columns]
    if leaked:
        raise AssertionError(f"post-treatment columns in the feature matrix: {leaked}")
    lift = (y[t == 1].mean() - y[t == 0].mean()) * 100
    return f"{len(x):,} rows, {x.shape[1]} features, naive lift {lift:.3f} pp"


def check_hillstrom_arms() -> str:
    hill = _needs("cvm.ingest.hillstrom", "1")
    x, y, t = hill.load()
    if not (0 < t.sum() < len(t)):
        raise AssertionError("one arm is empty; no treatment effect is identifiable")
    lift = (y[t == 1].mean() - y[t == 0].mean()) * 100
    return f"{len(x):,} rows, naive lift {lift:.2f} pp"


def check_online_retail() -> str:
    retail = _needs("cvm.ingest.online_retail", "1")
    df = retail.load()
    return f"{len(df):,} clean lines, {df['Customer ID'].nunique():,} customers"


def check_no_raw_identifiers() -> str:
    """Every landed Parquet must survive the MSISDN scan."""
    import pandas as pd

    hashing = _needs("cvm.ingest.hashing", "1")
    from cvm.config import settings

    landed = sorted(settings.interim_dir.glob("*.parquet"))
    if not landed:
        raise Pending("nothing landed yet; run python -m cvm.ingest.run")
    for path in landed:
        hashing.assert_no_raw_identifiers(pd.read_parquet(path))
    return f"{len(landed)} landed files clean: {[p.stem for p in landed]}"


# ---------------------------------------------------------------------------
# Phase 2 -- synthesis
# ---------------------------------------------------------------------------


def _population():
    import pandas as pd

    from cvm.config import settings

    path = settings.synthetic_dir / "population.parquet"
    if not path.exists():
        raise Pending(f"{path} not written; run `python -m cvm.synthesis.run` (see phase 2)")
    return pd.read_parquet(path)


def check_population_written() -> str:
    df = _population()
    from cvm.config import load_conf

    expected = load_conf("data")["synthesis"]["n_subscribers"]
    if len(df) != expected:
        raise AssertionError(f"{len(df):,} rows, config says {expected:,}")
    return f"{len(df):,} x {df.shape[1]} columns"


def check_generated_churn_rate() -> str:
    from cvm.config import load_conf

    df = _population()
    target = load_conf("market")["base"]["monthly_silent_churn_rate"]
    rate = float(df["silent_churn_30d"].mean())
    if abs(rate - target) > 0.005:
        raise AssertionError(f"{rate:.4f} against a {target:.4f} target")
    return f"{rate:.4f} (target {target:.4f})"


def check_recharge_ladder() -> str:
    from cvm.synthesis.quantile_map import assert_on_ladder, recharge_ladder

    df = _population()
    assert_on_ladder(df["modal_recharge_amount_lyd"].dropna())
    return f"every amount on {recharge_ladder()}"


def check_no_raw_identifiers_in_population() -> str:
    from cvm.ingest.hashing import assert_no_raw_identifiers

    df = _population()
    assert_no_raw_identifiers(df)
    if not df["subscriber_id_hashed"].is_unique:
        raise AssertionError("hashed ids are not unique")
    return f"{len(df):,} ids, unique, no MSISDN pattern"


def check_label_drivers_present() -> str:
    from cvm.synthesis.hazard import LABEL_DRIVER_FIELDS

    df = _population()
    missing = [f for f in LABEL_DRIVER_FIELDS if f not in df.columns]
    if missing:
        raise AssertionError(f"hazard drivers absent from the population: {missing}")
    return f"all {len(LABEL_DRIVER_FIELDS)} present"


def check_label_is_learnable() -> str:
    from cvm.synthesis.hazard import LABEL_DRIVER_FIELDS, assert_label_is_learnable

    df = _population()
    assert_label_is_learnable(df)
    strongest = max(
        (abs(float(df[f].corr(df["silent_churn_30d"]))), f)
        for f in LABEL_DRIVER_FIELDS
        if f in df.columns
    )
    return f"strongest driver {strongest[1]} at |r| {strongest[0]:.3f}"


def check_churn_window() -> str:
    """The 15-day gap: no churn date may fall inside it."""
    from cvm.config import load_conf

    df = _population()
    windows = load_conf("features")["windows"]
    start = windows["observation_days"] + windows["gap_days"]
    end = start + windows["outcome_days"]

    churned = df[df["silent_churn_30d"] == 1]["days_to_churn"]
    if not churned.between(start, end - 1).all():
        raise AssertionError(f"churn dates outside days {start}-{end - 1}")
    return f"all inside days {start}-{end - 1}, after a {windows['gap_days']}-day gap"


def check_reproducible() -> str:
    """The same seed must give the same population. Reproducibility is a
    stated deliverable, and a population that differs between runs makes every
    metric in the report unverifiable."""

    from cvm.synthesis.ctgan_engine import fit_and_sample
    from cvm.synthesis.run import build_real_backbone

    backbone = build_real_backbone().sample(3000, random_state=606).reset_index(drop=True)
    first, _ = fit_and_sample(backbone, kind="gaussian_copula", n=500)
    second, _ = fit_and_sample(backbone, kind="gaussian_copula", n=500)
    if not first.equals(second):
        differing = [c for c in first.columns if not first[c].equals(second[c])]
        raise AssertionError(f"two seeded runs differ on {differing}")
    return f"two seeded samples identical over {first.shape[1]} columns"


# ---------------------------------------------------------------------------
# Phases 3-10 -- declared now, so the check exists before the code does
# ---------------------------------------------------------------------------


def _pending(what: str, phase: str) -> Callable[[], str]:
    def check() -> str:
        raise Pending(f"{what}; see phase {phase}")

    return check


PHASES: dict[str, list[tuple[str, Callable[[], str]]]] = {
    "0": [
        ("python 3.11", check_python_version),
        ("key packages installed", check_packages),
        ("CVM_HASH_SALT set", check_salt),
        (".env not committable", check_env_is_ignored),
        ("test suite", check_tests),
        ("lint + format", check_lint),
        ("git remote", check_remote),
    ],
    "1": [
        ("UCI duplicate audit", check_uci_duplicates),
        ("UCI leaky field dropped", check_uci_leaky_field),
        ("Cell2Cell 1:1 join", check_cell2cell_join),
        ("Cell2Cell measured medians", check_cell2cell_distributions),
        ("IBM protected columns", check_ibm_protected_columns),
        ("Criteo arms + no post-treatment leak", check_criteo_arms),
        ("Hillstrom arms", check_hillstrom_arms),
        ("Online Retail II cleaning", check_online_retail),
        ("no raw identifiers landed", check_no_raw_identifiers),
    ],
    "2": [
        ("population written", check_population_written),
        ("generated churn rate ~3.5%", check_generated_churn_rate),
        ("recharge ladder respected", check_recharge_ladder),
        ("no raw identifiers", check_no_raw_identifiers_in_population),
        ("hazard drivers present", check_label_drivers_present),
        ("label is learnable", check_label_is_learnable),
        ("churn dates respect the gap", check_churn_window),
        ("generator is reproducible", check_reproducible),
    ],
    "3": [
        ("leakage suite fully green", _pending("feature store not built", "3")),
        ("point-in-time serving", _pending("feature store not built", "3")),
    ],
    "4": [
        ("benchmark table has 8 models", _pending("M1 not trained", "4")),
        ("calibration improves Brier", _pending("M1 not trained", "4")),
    ],
    "5": [("BG/NBD validated on holdout", _pending("M2 not built", "5"))],
    "6": [("Qini on Criteo > 0", _pending("M3 not built", "6"))],
    "7": [("advance safety guards green", _pending("M4 not built", "7"))],
    "8": [("endpoints return 200 not 501", _pending("decision engine not built", "8"))],
    "9": [("/health reports ok", _pending("models not loaded", "9"))],
    "10": [("docker compose up", _pending("not attempted", "10"))],
}


def run_phase(phase: str) -> tuple[int, int, int]:
    checks = PHASES[phase]
    print(f"\nPHASE {phase}")
    print("-" * 74)
    passed = failed = pending = 0
    for name, check in checks:
        try:
            detail = check()
            print(f"  {PASS}  {name:<38} {detail}")
            passed += 1
        except Pending as exc:
            print(f"  {PENDING}  {name:<38} {exc}")
            pending += 1
        except Exception as exc:
            print(f"  {FAIL}  {name:<38} {type(exc).__name__}: {exc}")
            failed += 1
    return passed, failed, pending


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("phase", nargs="?", help="Phase number (0-10). Omit for all.")
    args = ap.parse_args()

    if args.phase is not None and args.phase not in PHASES:
        print(f"Unknown phase {args.phase!r}. Known: {', '.join(PHASES)}")
        return 2

    phases = [args.phase] if args.phase else list(PHASES)
    totals = [0, 0, 0]
    for phase in phases:
        result = run_phase(phase)
        totals = [a + b for a, b in zip(totals, result, strict=True)]

    passed, failed, pending = totals
    print(f"\n{passed} passed, {failed} failed, {pending} pending")
    if failed:
        print("A FAIL means something that used to work is broken. Fix it before moving on.")
    elif pending:
        print("PENDING is expected -- it names the phase that has to land first.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
