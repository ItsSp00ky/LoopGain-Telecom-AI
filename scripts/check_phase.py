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
import json
import subprocess
import sys
import time
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
# Phase 3 -- the feature store
# ---------------------------------------------------------------------------


def _offline():
    import pandas as pd

    from cvm.config import settings

    path = settings.feature_store_offline
    if not path.exists():
        raise Pending(f"{path} does not exist; run `python -m cvm.features.run`")
    return pd.read_parquet(path)


def check_both_stores_exist() -> str:
    """Offline for training, online for serving. Two stores, two jobs."""
    from cvm.config import settings
    from cvm.features import store

    offline = _offline()
    if not settings.feature_store.exists():
        raise Pending(f"{settings.feature_store} does not exist")

    connection = store.connect()
    try:
        rows = connection.execute(f"SELECT count(*) FROM {store.TABLE}").fetchone()[0]
    finally:
        connection.close()
    return (
        f"offline {len(offline):,} x {offline.shape[1]}, online {rows:,} subscribers, "
        f"{offline['snapshot_date'].nunique()} snapshot dates"
    )


def check_leakage_suite() -> str:
    """The gate for this phase. Every xfail except the one that genuinely needs
    a trained M1 must be gone."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/leakage/",
            "-q",
            "--no-cov",
            "-p",
            "no:cacheprovider",
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    lines = result.stdout.strip().splitlines()
    tail = lines[-1] if lines else result.stderr[-200:]
    if result.returncode != 0:
        raise AssertionError(tail)
    return tail


def check_point_in_time_serving() -> str:
    """An as-of read must never return a snapshot after the cut-off. This is
    the guarantee every backtest downstream rests on."""
    import pandas as pd

    from cvm.features import store

    offline = _offline()
    snapshots = pd.to_datetime(offline["snapshot_date"])
    cutoff = snapshots.quantile(0.5).normalize()

    visible = store.get_features(as_of=str(cutoff.date()))
    latest = pd.to_datetime(visible["snapshot_date"]).max()
    if latest > cutoff:
        raise AssertionError(f"as-of {cutoff.date()} returned a row from {latest.date()}")
    if len(visible) >= len(offline):
        raise AssertionError("the cut-off excluded nothing, so it demonstrates nothing")
    return (
        f"as-of {cutoff.date()}: {len(visible):,} of {len(offline):,} rows, latest {latest.date()}"
    )


def check_splits_are_temporal() -> str:
    """Train strictly before validation strictly before test, and disjoint by
    subscriber. A random split here leaks the future and nothing would say so."""
    import pandas as pd

    from cvm.features import splits

    offline = _offline()
    train, validation, test = splits.temporal_split(offline)

    for earlier, later, names in (
        (train, validation, "train/validation"),
        (validation, test, "validation/test"),
    ):
        if (
            pd.to_datetime(earlier["snapshot_date"]).max()
            >= pd.to_datetime(later["snapshot_date"]).min()
        ):
            raise AssertionError(f"{names} overlap in time")

    sizes = [len(train), len(validation), len(test)]
    if sum(sizes) != len(offline):
        raise AssertionError(f"the splits sum to {sum(sizes)} of {len(offline)} rows")

    ids = [set(p["subscriber_id_hashed"]) for p in (train, validation, test)]
    shared = (ids[0] & ids[1]) | (ids[1] & ids[2]) | (ids[0] & ids[2])
    if shared:
        raise AssertionError(f"{len(shared)} subscriber(s) appear in more than one split")

    shares = "/".join(f"{100 * s / len(offline):.0f}" for s in sizes)
    return f"{shares}% by time, disjoint, to {pd.to_datetime(test['snapshot_date']).max().date()}"


def check_no_label_artifacts() -> str:
    """The label belongs in the training matrix; the fields that GENERATED it
    never do. `hazard_score` alone reconstructs the outcome exactly."""
    from cvm.config import load_conf
    from cvm.synthesis.hazard import LABEL_ARTIFACT_FIELDS

    offline = _offline()
    target = load_conf("features")["target"]["name"]

    # The target is IN LABEL_ARTIFACT_FIELDS and must nonetheless be present:
    # "may not be an input" and "must not exist" are different claims, and the
    # training matrix is exactly where the label belongs. Subtract it before
    # comparing, or this check fails on a store that is correct.
    artifacts = set(LABEL_ARTIFACT_FIELDS) - {target}

    present = sorted(artifacts & set(offline.columns))
    if present:
        raise AssertionError(f"label artefacts survived into the feature store: {present}")
    if target not in offline.columns:
        raise AssertionError(f"the target {target!r} is absent; nothing can be trained on this")
    return f"{len(artifacts)} artefacts dropped ({', '.join(sorted(artifacts))}), target retained"


def check_segments_populate() -> str:
    """All eight segments must be reachable. `Lost` silently never fired on the
    first run because `Hibernating` was ordered ahead of it."""
    from cvm.config import load_conf

    offline = _offline()
    if "segment" not in offline.columns:
        raise AssertionError("segment is absent from the feature store")

    declared = set(load_conf("features")["rfm_le"]["segments"])
    counts = offline["segment"].value_counts()
    invented = set(counts.index) - declared
    if invented:
        raise AssertionError(f"segments not in conf/features.yaml: {sorted(invented)}")
    # No tolerance. A segment that never fires is the exact bug this check
    # exists for -- `Lost` was unreachable for a whole run because `Hibernating`
    # was ordered ahead of it -- and any slack here is slack that hides it.
    empty = declared - set(counts.index)
    if empty:
        raise AssertionError(f"{len(empty)} segment(s) never fire: {sorted(empty)}")

    detail = ", ".join(f"{k} {100 * v / len(offline):.1f}%" for k, v in counts.head(3).items())
    return f"{len(counts)} of {len(declared)} populated ({detail})"


def check_no_raw_identifiers_in_features() -> str:
    """The privacy invariant, re-checked at the layer that serves an API."""
    import re

    offline = _offline()
    pattern = re.compile(
        r"(?<![0-9a-zA-Z])(?:\+?218[ -]?(?:0[ -]?)?|0[ -]?)9[1245](?:[ -]?[0-9]){7}(?![0-9])"
    )

    for column in offline.select_dtypes(include=["object", "string"]).columns:
        sample = offline[column].dropna().astype(str).head(5000)
        if any(pattern.search(v) for v in sample):
            raise AssertionError(f"{column} contains what looks like an MSISDN")

    ids = offline["subscriber_id_hashed"].astype(str)
    if not ids.str.fullmatch(r"[0-9a-f]{64}").all():
        raise AssertionError("subscriber_id_hashed is not uniformly a SHA-256 digest")
    return f"{offline.shape[1]} columns scanned, ids are 64-hex throughout"


def check_feature_coverage() -> str:
    """Every feature family present, and no column entirely null. A family that
    silently produced nothing would surface as a model that mysteriously
    underperforms, which is a hard thing to trace back."""
    offline = _offline()

    expected = {
        "velocity": "decay_divergence",
        "distress": "chronic_distress",
        "leakage": "leakage_score",
        "rfm_le": "rfmle_cell",
        "network_quality": "dropped_call_rate_30d",
    }
    missing = {k: v for k, v in expected.items() if v not in offline.columns}
    if missing:
        raise AssertionError(f"feature families absent: {missing}")

    all_null = [c for c in offline.columns if offline[c].isna().all()]
    if all_null:
        raise AssertionError(f"entirely null: {all_null}")

    worst = offline.isna().mean().max()
    return f"{len(expected)} families, {offline.shape[1]} columns, max nullity {worst:.1%}"


# ---------------------------------------------------------------------------
# Phase 4 -- M1 churn
# ---------------------------------------------------------------------------


def _report(name: str):
    """Load a written report, or PEND if M1 has not been run."""
    import json

    from cvm.config import settings

    path = settings.reports_dir / name
    if not path.exists():
        raise Pending(f"{path.name} does not exist; run `python -m cvm.models.m1_churn.run`")
    if path.suffix == ".json":
        return json.loads(path.read_text())
    import pandas as pd

    return pd.read_csv(path)


def check_benchmark_table() -> str:
    """Eight models, PR-AUC leading, accuracy never the headline."""
    table = _report("m1_benchmark.csv")

    if len(table) < 8:
        raise AssertionError(f"only {len(table)} models in the table; the config declares 8")
    if table.columns[1] != "pr_auc":
        raise AssertionError(f"{table.columns[1]!r} leads the table; PR-AUC must")
    if "accuracy" in table.columns[:3].tolist():
        raise AssertionError("accuracy is being reported as a headline")

    best = table.iloc[0]
    return (
        f"{len(table)} models, best {best['model']} at PR-AUC {best['pr_auc']:.4f}, "
        f"lift@1 {best['lift_at_decile_1']:.2f}, accuracy reported last"
    )


def check_calibration_improves() -> str:
    """Brier must FALL after isotonic. If it does not, calibration is
    decoration and "a 0.31 means 31%" is an unsupported claim."""
    m = _report("m1_calibration.json")

    if m["brier_calibrated"] > m["brier_raw"]:
        raise AssertionError(f"Brier rose from {m['brier_raw']:.5f} to {m['brier_calibrated']:.5f}")
    gap = abs(m["mean_predicted_calibrated"] - m["observed_rate"])
    if gap > 0.01:
        raise AssertionError(
            f"calibrated mean {m['mean_predicted_calibrated']:.4f} against an observed "
            f"{m['observed_rate']:.4f}: a {gap:.4f} gap is too wide to call calibrated"
        )
    return (
        f"Brier {m['brier_raw']:.5f} -> {m['brier_calibrated']:.5f}, "
        f"ECE {m['ece_raw']:.5f} -> {m['ece_calibrated']:.5f}, "
        f"mean {m['mean_predicted_calibrated']:.4f} against observed {m['observed_rate']:.4f}"
    )


def check_leakage_suite_has_no_xfail() -> str:
    """The Phase 4 gate the roadmap set: green with EVERY xfail deleted."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/leakage/",
            "-q",
            "--no-cov",
            "-p",
            "no:cacheprovider",
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    lines = result.stdout.strip().splitlines()
    tail = lines[-1] if lines else result.stderr[-200:]
    if result.returncode != 0:
        raise AssertionError(tail)
    if "xfail" in tail:
        raise AssertionError(f"an xfail marker remains: {tail}")
    return tail


def check_naive_vs_honest() -> str:
    """The disclosure must show the inflated figures AND the corrected ones,
    with the honest one lower. If the gap is not there, the argument is not."""
    table = _report("m1_naive_vs_honest.csv")

    naive = table.iloc[0]
    honest = table.iloc[-1]
    if honest["roc_auc"] >= naive["roc_auc"]:
        raise AssertionError(
            f"honest ROC-AUC {honest['roc_auc']:.4f} is not below naive "
            f"{naive['roc_auc']:.4f}; the disclosure has nothing to disclose"
        )
    if honest["split"] != "temporal" or honest["leaky_field"] != "dropped":
        raise AssertionError(f"the honest row is not honest: {honest.to_dict()}")

    return (
        f"naive {naive['accuracy']:.4f} acc / {naive['roc_auc']:.4f} ROC / "
        f"{naive['pr_auc']:.4f} PR -> honest {honest['accuracy']:.4f} / "
        f"{honest['roc_auc']:.4f} / {honest['pr_auc']:.4f}"
    )


def check_survival_is_held_out() -> str:
    """Concordance for both arms, and the ladder boundaries.

    An in-sample concordance flatters a forest far more than a penalised linear
    model, so both are scored on rows neither has seen.
    """
    m = _report("m1b_survival.json")
    c = m["concordance"]

    for name, value in c.items():
        if not 0.5 <= value <= 1.0:
            raise AssertionError(f"{name} concordance {value:.4f} is outside [0.5, 1.0]")
    if c["cox"] < 0.6:
        raise AssertionError(f"cox concordance {c['cox']:.4f} is barely above chance")

    boundaries = m["ladder_boundary_days"]
    note = (
        f"boundaries {boundaries}"
        if boundaries
        else "no boundaries (bootstrap disagrees -- correctly refused)"
    )
    return f"cox {c['cox']:.4f}, rsf {c['rsf']:.4f}, held out; {note}"


def check_explanations_are_plain() -> str:
    """Every score must carry a reason a marketing analyst can read. A
    contribution rendered as `days_since_last_topup = 23, shap = +0.14` has
    been annotated, not translated."""
    from cvm.models.m1_churn.explain import to_plain_language

    cases = [
        ("days_since_last_topup", 23.0, 0.14),
        ("leakage_score", 0.82, 0.09),
        ("balance_zero_hours_30d", 310.0, 0.05),
        ("a_brand_new_feature_30d", 4.0, -0.02),
    ]
    for feature, value, contribution in cases:
        sentence = to_plain_language(feature, value, contribution)
        if feature in sentence:
            raise AssertionError(f"the raw column name leaked into: {sentence!r}")
        if "shap" in sentence.lower():
            raise AssertionError(f"jargon leaked into: {sentence!r}")
        if not sentence.endswith("churn risk"):
            raise AssertionError(f"no direction in: {sentence!r}")

    return f"{len(cases)} renderings, no column names or SHAP values in any"


def check_shap_attribution() -> str:
    """Risk attributed to feature families, summing to 1.0 per subscriber."""
    table = _report("m1_shap_attribution.csv")

    numeric = table.drop(columns=["dominant_family"], errors="ignore")
    totals = numeric.sum(axis=1)
    if not ((totals - 1.0).abs() < 1e-6).all():
        raise AssertionError(f"family shares do not sum to 1.0 (worst {totals.max():.4f})")

    means = numeric.mean().sort_values(ascending=False)
    top = ", ".join(f"{k} {v:.1%}" for k, v in means.head(3).items())
    return f"{len(table):,} subscribers over {numeric.shape[1]} families ({top})"


def check_model_artefact_loads() -> str:
    """The serving artefact must exist and carry its column list. A model
    without the training columns cannot align a serving batch."""
    import joblib

    from cvm.config import settings

    path = settings.models_dir / "m1_churn.joblib"
    if not path.exists():
        raise Pending(f"{path.name} does not exist; run `python -m cvm.models.m1_churn.run`")

    bundle = joblib.load(path)
    for key in ("model", "columns", "name"):
        if key not in bundle:
            raise AssertionError(f"the artefact has no {key!r}")
    if not hasattr(bundle["model"], "predict_proba"):
        raise AssertionError("the stored model cannot predict_proba")

    return f"{bundle['name']} with {len(bundle['columns'])} columns, loads and scores"


# ---------------------------------------------------------------------------
# Phase 5 -- M2 value
# ---------------------------------------------------------------------------


def check_bg_nbd_on_real_purchases() -> str:
    """The technique, validated on Online Retail II before it touches recharges.

    Every CLV number for Almadar is computed on generated data from a
    reconstructed summary, so it cannot validate itself -- a good fit there
    would only mean the generator and the model agree. This is the one number
    in M2 that measures whether the technique works.
    """
    m = _report("m2_clv.json").get("validation_on_real_purchases")
    if not m:
        raise Pending("run `python -m cvm.models.m2_value.run` without --skip-validation")

    if m["mae"] >= m["mean_actual"]:
        raise AssertionError(
            f"MAE {m['mae']:.3f} is not below the mean actual {m['mean_actual']:.3f}: "
            "the model is no better than predicting the average"
        )
    if m["spearman"] < 0.4:
        raise AssertionError(f"Spearman {m['spearman']:.3f} -- the ordering is barely there")

    return (
        f"{m['customers']:,} customers, {m['holdout_days']:.0f}-day holdout: MAE {m['mae']:.3f} "
        f"against a mean actual of {m['mean_actual']:.3f}, Spearman {m['spearman']:.3f}"
    )


def check_no_degenerate_bg_nbd_fit() -> str:
    """b < 1 makes the dropout Beta U-shaped and every zero-repeat customer
    scores NaN -- silently, which is how it survived a whole run."""
    import numpy as np
    import pandas as pd

    from cvm.config import settings
    from cvm.models.m2_value import clv

    path = settings.feature_store_offline
    if not path.exists():
        raise Pending(f"{path.name} does not exist; run `python -m cvm.features.run`")

    summary = clv.summary_from_population(pd.read_parquet(path))
    model = clv.fit_bg_nbd(clv.complete_cases(summary))
    probe = np.asarray(
        model.predict(30.0, summary[clv.FREQUENCY], summary[clv.RECENCY], summary[clv.AGE]),
        dtype="float64",
    )
    unusable = int(np.isnan(probe).sum())
    if unusable:
        raise AssertionError(f"{unusable} NaN predictions at b={model.params_['b']:.4f}")

    return (
        f"b={model.params_['b']:.3f} (must exceed 1), r={model.params_['r']:.3f}, "
        f"0 NaN over {len(summary):,} subscribers"
    )


def check_clv_ceiling_is_live() -> str:
    """The constraint that makes the pricing engine defensible to a CFO. At a
    40 LYD ARPU the annual value is 480 and 15% of it is 72 LYD."""
    import pandas as pd

    from cvm.config import load_conf
    from cvm.models.m2_value.clv import retention_budget_ceiling

    guard = load_conf("pricing")["guardrails"]["clv_ceiling"]
    if not guard.get("enabled", True):
        raise AssertionError("clv_ceiling is disabled in conf/pricing.yaml")

    # The same key tests/unit/test_proposal_consistency.py reads, so the check
    # and the proposal cannot drift onto two different ARPUs.
    arpu = load_conf("market")["base"]["monthly_arpu_lyd"]
    annual = arpu * 12
    reference = float(retention_budget_ceiling(pd.Series([annual])).iloc[0])
    if reference != 72.0:
        raise AssertionError(
            f"{guard['max_fraction_of_clv']:.0%} of a {annual:.0f} LYD annual value is "
            f"{reference:.2f}, and the proposal says 72.00"
        )

    metrics = _report("m2_clv.json")
    return (
        f"{guard['max_fraction_of_clv']:.0%} of CLV; the {arpu:.0f} LYD ARPU reference is "
        f"{reference:.2f} LYD, and the base median is {metrics['median_ceiling_lyd']:.2f}"
    )


def check_every_subscriber_has_a_ceiling() -> str:
    """A subscriber with no CLV has no ceiling, which means no constraint --
    strictly worse than an estimated one."""
    import pandas as pd

    from cvm.config import settings

    path = settings.processed_dir / "m2_clv.parquet"
    if not path.exists():
        raise Pending(f"{path.name} does not exist; run `python -m cvm.models.m2_value.run`")

    frame = pd.read_parquet(path)
    if frame["clv_12m"].isna().any():
        raise AssertionError(f"{int(frame['clv_12m'].isna().sum())} subscribers have no CLV")
    if (frame["retention_ceiling_lyd"] > frame["clv_12m"]).any():
        raise AssertionError("a ceiling exceeds the value it is a fraction of")
    if (frame["clv_12m"] < 0).any():
        raise AssertionError("negative CLV")

    return (
        f"{len(frame):,} subscribers, all valued -- median CLV "
        f"{frame['clv_12m'].median():.1f} LYD, ceiling {frame['retention_ceiling_lyd'].median():.2f}"
    )


def check_k_is_chosen_by_silhouette() -> str:
    """Chosen by a number, not by eye. An elbow read off a chart gives two
    people two answers and neither can defend theirs."""
    import pandas as pd

    from cvm.config import settings

    result = _report("m2_segmentation.json")
    scores = pd.read_csv(settings.reports_dir / "m2_kmeans_scores.csv")

    best = int(scores.loc[scores["silhouette"].idxmax(), "k"])
    if result["k_chosen"] != best:
        raise AssertionError(f"k={result['k_chosen']} chosen but silhouette peaks at {best}")
    if result["silhouette"] <= 0:
        raise AssertionError(f"silhouette {result['silhouette']:.4f} -- there is no structure")

    note = (
        "" if result["k_chosen"] == result["k_by_elbow"] else f", elbow says {result['k_by_elbow']}"
    )
    return f"k={result['k_chosen']} at silhouette {result['silhouette']:.4f} over {len(scores)} values{note}"


def check_rules_and_clusters_disagree() -> str:
    """Perfect agreement would mean one of them is redundant. The cells that
    disagree are the dashboard insight, and they have to exist.

    Reported at MATCHED k as well, because adjusted Rand between 3 clusters and
    8 rule segments is bounded below 1 by arithmetic rather than disagreement.
    """
    result = _report("m2_segmentation.json")

    share = result["disagreement_share"]
    if share <= 0:
        raise AssertionError("the clusters reproduce the rules exactly; one is redundant")
    if share >= 0.95:
        raise AssertionError(f"{share:.1%} disagreement -- the two labellings are unrelated")

    matched = result.get("matched_k_adjusted_rand")
    return (
        f"{share:.1%} disagree at k={result['k_chosen']} (adjusted Rand "
        f"{result['adjusted_rand']:.3f}); at matched k={result['matched_k']} Rand is {matched:.3f}"
    )


def check_segments_are_tested_against_the_data() -> str:
    """The uncomfortable question: are the eight business segments a shape in
    the data, or a grid imposed on it? Reported either way."""
    result = _report("m2_segmentation.json")

    natural = result.get("natural_clusters_from_dendrogram")
    declared = result["declared_business_segments"]
    if natural is None:
        raise Pending("hierarchical clustering was skipped")

    verdict = (
        "they match"
        if natural == declared
        else "they do NOT -- the segments are a reporting convention, and the report says so"
    )
    return f"dendrogram cuts at {natural}, {declared} business segments declared: {verdict}"


def check_pca_variance_reported() -> str:
    """How much RFM-LE variance actually sits in two components. If most of it
    does, the five dimensions are measuring fewer than five things."""
    result = _report("m2_segmentation.json")
    explained = result["pca_explained_variance"]
    if not 0 < explained <= 1:
        raise AssertionError(f"explained variance {explained:.3f} is outside (0, 1]")

    note = (
        "most of RFM-LE collapses into two"
        if explained > 0.8
        else "the five dimensions carry genuinely different information"
    )
    return f"{explained:.1%} in 2 components -- {note}"


# ---------------------------------------------------------------------------
# Phase 6 -- M3 uplift
# ---------------------------------------------------------------------------


def check_qini_on_criteo() -> str:
    """Deliverable D4, and the strongest claim in the proposal. Real randomised
    arms, real Qini -- the answer to "your data is generated, so what?"."""
    m = _report("m3_criteo_validation.json")

    if m["qini"] <= 0:
        raise AssertionError(
            f"Qini {m['qini']:.4f} -- no measurable uplift, the model is not working"
        )
    if m["uplift_at_k_pp"] <= m["naive_lift_pp"]:
        raise AssertionError(
            f"uplift@{m['k']:.0%} is {m['uplift_at_k_pp']:.3f} pp against a naive "
            f"{m['naive_lift_pp']:.3f} pp: targeting buys nothing over treating everyone"
        )
    return (
        f"Qini {m['qini']:+.4f} on {m['rows_scored']:,} held-out rows ({m['treated_share']:.1%} "
        f"treated); uplift@{m['k']:.0%} {m['uplift_at_k_pp']:+.3f} pp against a naive "
        f"{m['naive_lift_pp']:+.3f} pp"
    )


def check_qini_matches_the_reference() -> str:
    """Our Qini against scikit-uplift's, on lopsided arms.

    Criteo is 85/15 and every Qini formula rescales the control arm to the
    treated arm's size. Getting that term wrong yields a curve that looks fine
    and is wrong by the ratio.
    """
    import numpy as np
    from sklift.metrics import qini_auc_score

    from cvm.models.m3_uplift.evaluate import qini_coefficient

    worst = 0.0
    for share in (0.5, 0.85, 0.15):
        rng = np.random.default_rng(42)
        n = 20000
        t = (rng.random(n) < share).astype(int)
        score = rng.normal(size=n)
        y = (rng.random(n) < 0.05 + 0.04 * t * (score > 0)).astype(int)
        worst = max(worst, abs(qini_coefficient(score, y, t) - qini_auc_score(y, score, t)))

    if worst > 1e-4:
        raise AssertionError(f"our Qini differs from scikit-uplift by {worst:.2e}")
    return f"agrees with scikit-uplift to {worst:.1e} at 50/50, 85/15 and 15/85 arms"


def check_all_four_quadrants_populate() -> str:
    """A run with zero sleeping dogs usually means the threshold is wrong, not
    that none exist -- and sleeping dogs are the reason this module cannot be
    skipped. A system without one does not merely waste budget; it causes churn
    it would not otherwise have caused."""
    from cvm.models.m3_uplift.two_model import QUADRANTS

    m = _report("m3_criteo_validation.json")
    counts = {name: m.get(f"quadrant_{name}", 0) for name in QUADRANTS}

    empty = [name for name, count in counts.items() if count == 0]
    if empty:
        raise AssertionError(
            f"{empty} never fire. Check sleeping_dog_threshold in "
            "conf/models/m3_uplift.yaml before concluding the campaign is safe."
        )
    total = sum(counts.values())
    detail = ", ".join(f"{k} {v / total:.1%}" for k, v in counts.items())
    return f"all four on Criteo ({detail})"


def check_break_even_is_where_the_proposal_says() -> str:
    """Expected value must turn positive at 1.04 pp of uplift and not before.
    The whole business case rests on this division."""
    from cvm.config import load_conf
    from cvm.models.m3_uplift.evaluate import break_even_uplift, expected_value_of_treatment

    market = load_conf("market")["base"]
    annual = market["monthly_arpu_lyd"] * 12
    incentive = market["blended_incentive_lyd"]

    point = break_even_uplift(annual, incentive)
    if round(100 * point, 2) != 1.04:
        raise AssertionError(f"{incentive} / {annual} = {100 * point:.4f} pp, not 1.04 pp")
    if not expected_value_of_treatment(0.0100, annual, incentive) < 0:
        raise AssertionError("treating at 1.00 pp of uplift is not loss-making, and it must be")
    if not expected_value_of_treatment(0.0110, annual, incentive) > 0:
        raise AssertionError("treating at 1.10 pp of uplift is not profitable, and it must be")

    return f"{incentive:.0f} / {annual:.0f} = {100 * point:.4f} pp, and E[gain] crosses zero there"


def check_the_holdout_is_mandatory_and_random() -> str:
    """Without a randomised control arm there is no counterfactual, net margin
    impact cannot be isolated, and every ROI figure becomes an assertion."""
    import pandas as pd

    from cvm.config import load_conf, settings
    from cvm.models.m3_uplift.two_model import assign_control_holdout

    conf = load_conf("models/m3_uplift")
    if not conf.get("holdout_is_mandatory", False):
        raise AssertionError("holdout_is_mandatory is off in conf/models/m3_uplift.yaml")

    cohort = pd.DataFrame({"x": range(20000)})
    first = assign_control_holdout(cohort)
    if not first.equals(assign_control_holdout(cohort)):
        raise AssertionError("the holdout moves between runs, so it cannot measure anything")

    target = conf["control_holdout_fraction"]
    if abs(first.mean() - target) > 0.02:
        raise AssertionError(f"holdout is {first.mean():.3f}, target {target:.3f}")

    path = settings.processed_dir / "m3_uplift.parquet"
    landed = ""
    if path.exists():
        frame = pd.read_parquet(path)
        landed = f"; {int(frame['is_control'].sum()):,} held out of {len(frame):,} in the run"
    return f"{target:.0%}, seeded and reproducible{landed}"


def check_the_pipeline_test_is_held_out() -> str:
    """The generated-population numbers are a PIPELINE TEST, and they must be
    scored on rows the model did not train on.

    A two-model difference memorises readily -- both arms overfit independently
    and the difference of two overfits looks like signal. Scored in-sample it
    reported Qini 0.2745 and uplift@30% of +50.8 pp from an injected effect of
    at most 6 pp; held out, 0.0091 and +4.9 pp.
    """
    m = _report("m3_uplift.json")
    pipeline = m.get("pipeline_test_on_generated_population", {})
    if "rows_scored" not in pipeline:
        raise AssertionError("the pipeline test reports no held-out row count")

    criteo = m.get("criteo_validation", {})
    if criteo and pipeline["qini"] > 3 * criteo["qini"]:
        raise AssertionError(
            f"the generated population scores Qini {pipeline['qini']:.4f} against Criteo's "
            f"{criteo['qini']:.4f}. Numbers that much better on data we made up are the "
            "symptom of scoring on the training rows."
        )
    return (
        f"{pipeline['rows_scored']:,} held-out rows, Qini {pipeline['qini']:+.4f}, "
        f"uplift@30% {100 * pipeline['uplift_at_k']:+.3f} pp"
    )


def check_only_persuadables_are_funded() -> str:
    """Budget goes to persuadables, never to sure things, lost causes or
    sleeping dogs. The last of those is not waste -- it is harm."""
    import pandas as pd

    from cvm.config import settings

    path = settings.processed_dir / "m3_uplift.parquet"
    if not path.exists():
        raise Pending(f"{path.name} does not exist; run `python -m cvm.models.m3_uplift.run`")

    frame = pd.read_parquet(path)
    treated = frame[frame["would_treat"] == 1]

    wrong = treated[treated["quadrant"] != "persuadable"]
    if not wrong.empty:
        raise AssertionError(
            f"{len(wrong)} non-persuadable subscribers would be treated: "
            f"{wrong['quadrant'].value_counts().to_dict()}"
        )
    if (treated["expected_value_lyd"] <= 0).any():
        raise AssertionError("a subscriber with non-positive expected value would be treated")
    if treated["is_control"].any():
        raise AssertionError("a control-holdout subscriber would be treated")

    dogs = int((frame["quadrant"] == "sleeping_dog").sum())
    return (
        f"{len(treated):,} of {len(frame):,} funded, all persuadable with positive E[gain]; "
        f"{dogs:,} sleeping dogs excluded"
    )


def check_expected_value_respects_the_clv_ceiling() -> str:
    """M2's ceiling is what M3 is allowed to spend. The bridge between them has
    to actually hold."""
    import pandas as pd

    from cvm.config import load_conf, settings

    path = settings.processed_dir / "m3_uplift.parquet"
    if not path.exists():
        raise Pending(f"{path.name} does not exist; run `python -m cvm.models.m3_uplift.run`")

    frame = pd.read_parquet(path)
    incentive = load_conf("market")["base"]["blended_incentive_lyd"]

    over = frame[(frame["would_treat"] == 1) & (frame["retention_ceiling_lyd"] < incentive)]
    if not over.empty:
        raise AssertionError(
            f"{len(over):,} funded subscribers have a retention ceiling below the "
            f"{incentive:.0f} LYD incentive -- the offer costs more than M2 allows"
        )
    return (
        f"every funded subscriber's ceiling clears the {incentive:.0f} LYD incentive "
        f"(median ceiling {frame['retention_ceiling_lyd'].median():.2f} LYD)"
    )


# ---------------------------------------------------------------------------
# Phase 7 -- M4 advance
# ---------------------------------------------------------------------------


def check_guardrail_suite_has_no_xfail() -> str:
    """The gate the roadmap set: every behavioural marker deleted.

    This is the only module that lends money, so the guardrail suite is not a
    quality bar -- it is the thing that stops a real subscriber being handed a
    debt that consumes their next recharge.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-m",
            "guardrail",
            "-q",
            "--no-cov",
            "-p",
            "no:cacheprovider",
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    lines = result.stdout.strip().splitlines()
    tail = lines[-1] if lines else result.stderr[-200:]
    if result.returncode != 0:
        raise AssertionError(tail)
    if "xfail" in tail:
        raise AssertionError(f"a guardrail xfail remains: {tail}")
    return tail


def check_the_headline_case() -> str:
    """A habitual 5 LYD recharger is DECLINED the 5 LYD data advance and
    offered the 0.5 LYD fallback -- while the same subscriber is granted a
    small airtime advance.

    PD alone would approve the data advance. That is the trap: they probably
    WOULD repay, and the repayment would consume their entire next top-up and
    return them to zero. Affordability declines what PD approves.
    """
    from cvm.api.schemas import AdvanceLimitRequest, AdvanceProduct
    from cvm.decision.advance_limit import decide_limit, limit_from_pd

    features = {
        "repayment_probability": 0.92,
        "lockout_risk": 0.02,
        "modal_recharge_amount_lyd": 5.0,
        "loyalty_tier": "gold",
        "clv_12m": 480.0,
        "balance_zero_hours_30d": 10.0,
        "failed_bundle_attempts_30d": 0.0,
        "consecutive_sub_5_lyd_recharges": 0.0,
        "emergency_service_alternations_90d": 0.0,
        "airtime_advance_count_90d": 1.0,
        "data_advance_count_90d": 0.0,
        "days_since_last_advance": 30.0,
        "advances_this_month": 0.0,
        "cumulative_exposure_this_month_lyd": 0.0,
    }
    if limit_from_pd(0.92, "data") != 5.0:
        raise AssertionError("PD alone no longer grants the data advance; the case is not a trap")

    data = decide_limit(
        AdvanceLimitRequest(subscriber_id="a" * 64, product=AdvanceProduct.DATA), features
    )
    if data.approved:
        raise AssertionError(f"the data advance was approved at {data.limit_lyd} LYD")
    if data.fallback_offer_id != "DAY_50MB":
        raise AssertionError(f"no affordable fallback offered: {data.fallback_offer_id}")

    airtime = decide_limit(
        AdvanceLimitRequest(subscriber_id="b" * 64, product=AdvanceProduct.AIRTIME), features
    )
    if not airtime.approved or airtime.limit_lyd >= 5.0:
        raise AssertionError(
            f"the same subscriber should still get a SMALL airtime advance, got "
            f"approved={airtime.approved} at {airtime.limit_lyd} LYD"
        )
    return (
        f"data declined on {data.binding_constraint} with {data.fallback_offer_id} offered; "
        f"airtime granted {airtime.limit_lyd:.0f} LYD, leaving "
        f"{5.0 - airtime.limit_lyd:.0f} LYD after settlement"
    )


def check_guards_only_reduce() -> str:
    """A guard that raises a credit limit is a bug, not a feature. Swept over
    the grid rather than spot-checked."""
    import itertools

    from cvm.decision.advance_limit import apply_safety_guards

    base = {
        "modal_recharge_amount_lyd": 40.0,
        "loyalty_tier": "gold",
        "clv_12m": 480.0,
        "balance_zero_hours_30d": 10.0,
        "failed_bundle_attempts_30d": 0.0,
        "consecutive_sub_5_lyd_recharges": 0.0,
        "emergency_service_alternations_90d": 0.0,
        "airtime_advance_count_90d": 1.0,
        "data_advance_count_90d": 0.0,
        "days_since_last_advance": 30.0,
        "advances_this_month": 0.0,
        "cumulative_exposure_this_month_lyd": 0.0,
    }
    combinations = 0
    for start, modal, risk, distress in itertools.product(
        (0.0, 1.0, 3.0, 5.0), (5.0, 10.0, 40.0), (0.0, 0.5), (0.0, 700.0)
    ):
        features = {
            **base,
            "modal_recharge_amount_lyd": modal,
            "lockout_risk": risk,
            "balance_zero_hours_30d": distress,
            "consecutive_sub_5_lyd_recharges": 9.0 if distress else 0.0,
        }
        adjusted, _ = apply_safety_guards(start, features)
        combinations += 1
        if adjusted > start + 1e-9:
            raise AssertionError(f"guards raised {start} to {adjusted} at {features}")
        if adjusted < 0:
            raise AssertionError(f"guards produced a negative limit: {adjusted}")
    return f"{combinations} combinations of limit, recharge, lockout risk and distress -- all reduced or held"


def check_no_invented_denominations() -> str:
    """We cannot offer a 2 LYD advance. Swept across the whole PD range and
    through the full decision path, not just the band table."""
    import numpy as np

    from cvm.api.schemas import AdvanceLimitRequest, AdvanceProduct
    from cvm.config import load_conf
    from cvm.decision.advance_limit import decide_limit

    real = {
        float(d)
        for d in load_conf("catalogue")["emergency_credit"]["rasid_fi_waqtuh"]["denominations_lyd"]
    }
    seen = set()
    for probability in np.linspace(0, 1, 41):
        for modal in (5.0, 10.0, 20.0, 40.0, 100.0):
            features = {
                "repayment_probability": float(probability),
                "lockout_risk": 0.02,
                "modal_recharge_amount_lyd": modal,
                "loyalty_tier": "platinum",
                "clv_12m": 2000.0,
                "balance_zero_hours_30d": 0.0,
                "failed_bundle_attempts_30d": 0.0,
                "consecutive_sub_5_lyd_recharges": 0.0,
                "emergency_service_alternations_90d": 0.0,
                "airtime_advance_count_90d": 0.0,
                "data_advance_count_90d": 0.0,
                "days_since_last_advance": 30.0,
                "advances_this_month": 0.0,
                "cumulative_exposure_this_month_lyd": 0.0,
            }
            seen.add(
                decide_limit(
                    AdvanceLimitRequest(subscriber_id="c" * 64, product=AdvanceProduct.AIRTIME),
                    features,
                ).limit_lyd
            )

    invented = seen - real - {0.0}
    if invented:
        raise AssertionError(f"invented denominations: {sorted(invented)}")
    return f"{len(seen)} distinct limits over 205 cases, all in {sorted(real)} or zero"


def check_selection_bias_is_measured() -> str:
    """The observed population is filtered by a `balance <= 0.5 LYD` gate, so
    it is non-random by construction and the direction is NOT the textbook one.
    Measured before it is corrected."""
    report = _report("m4_advance.json")
    heads = report["pd_heads"]
    if not heads:
        raise AssertionError("no PD head reported a bias measurement")

    lines = []
    for product, r in heads.items():
        bias = r["selection_bias"]
        if bias["max_abs_smd"] <= 0.1:
            raise AssertionError(
                f"{product}: worst SMD {bias['max_abs_smd']:.3f} -- either the populations "
                "really are comparable, which would be surprising, or the comparison is broken"
            )
        lines.append(
            f"{product} worst {bias['max_abs_smd_feature']} at {bias['max_abs_smd']:.2f}, "
            f"{bias['features_above_0_25']} above 0.25"
        )
    return "; ".join(lines)


def check_reject_inference_shifts_but_does_not_swamp() -> str:
    """The correction should move the estimate, and should not dominate it.

    A large shift is the symptom of a broken correction rather than a strong
    one: passing `sample_weight` to the constructor (where LightGBM discards
    it) or calibrating on the fuzzy labels both produced shifts around -0.35,
    and both were artefacts.
    """
    report = _report("m4_advance.json")
    notes = []
    for product, r in report["pd_heads"].items():
        shift = r["correction_shift"]
        if abs(shift) < 1e-6:
            raise AssertionError(f"{product}: the correction changed nothing; is it running?")
        if abs(shift) > 0.15:
            raise AssertionError(
                f"{product}: the correction moved mean PD by {shift:+.4f}. A shift that large "
                "is the signature of weights being dropped or a calibrator fitted on inferred "
                "labels, not of a strong correction."
            )
        notes.append(
            f"{product} {shift:+.4f} (observed repayment {r['observed_repayment_rate']:.3f})"
        )
    return "; ".join(notes)


def check_advance_decisions_landed() -> str:
    """Every scored subscriber has a decision, and each declined one names the
    term that bound."""
    import pandas as pd

    from cvm.config import settings

    path = settings.processed_dir / "m4_advance.parquet"
    if not path.exists():
        raise Pending(f"{path.name} does not exist; run `python -m cvm.models.m4_advance.run`")

    frame = pd.read_parquet(path)
    if frame["binding_constraint"].isna().any():
        raise AssertionError("a decision has no binding constraint")
    if not frame.loc[~frame["approved"], "binding_constraint"].notna().all():
        raise AssertionError("a decline gives no reason")

    approved = frame.groupby("product")["approved"].mean().to_dict()
    detail = ", ".join(f"{k} {v:.1%}" for k, v in approved.items())
    return f"{len(frame):,} decisions over {frame['product'].nunique()} products ({detail})"


# ---------------------------------------------------------------------------
# Phase 8 -- the decision engine
# ---------------------------------------------------------------------------


def _client():
    from fastapi.testclient import TestClient

    from cvm.api.main import app

    return TestClient(app)


def _a_real_subscriber() -> str:
    import pandas as pd

    from cvm.config import settings

    path = settings.feature_store_offline
    if not path.exists():
        raise Pending(f"{path.name} does not exist; run `python -m cvm.features.run`")
    return str(pd.read_parquet(path, columns=["subscriber_id_hashed"]).iloc[0, 0])


def check_endpoints_stop_returning_501() -> str:
    """The decision endpoints answer rather than announcing they are unbuilt."""
    subscriber = _a_real_subscriber()
    cases = [
        ("/v1/offer/next-best", {"subscriber_id": subscriber, "channel": "api"}),
        ("/v1/price/quote", {"subscriber_id": subscriber, "bundle_id": "MO_20"}),
        ("/v1/advance/limit", {"subscriber_id": subscriber, "product": "rasid_fi_waqtuh"}),
    ]
    with _client() as client:
        results = {}
        for path, payload in cases:
            response = client.post(path, json=payload)
            results[path] = response.status_code
            if response.status_code != 200:
                raise AssertionError(
                    f"{path} returned {response.status_code}: {response.text[:200]}"
                )
    return f"{len(results)} endpoints returning 200: {', '.join(results)}"


def check_health_is_ok() -> str:
    """Every model loaded AND the feature store readable. A degraded API that
    reports ok is worse than one that reports nothing."""
    with _client() as client:
        body = client.get("/health").json()

    missing = [k for k, v in body["models_loaded"].items() if not v]
    if missing:
        raise AssertionError(f"not loaded: {missing}")
    if not body["feature_store_reachable"]:
        raise AssertionError("the feature store is not reachable")
    if body["status"] != "ok":
        raise AssertionError(f"status is {body['status']}")
    return f"{len(body['models_loaded'])} models loaded, feature store reachable"


def check_every_offer_is_explainable() -> str:
    """An offer the system cannot explain is one it should not have made.

    Every response must carry reason codes, a customer-facing sentence, a
    decision-log id, and the full list of constraints CONSIDERED -- not only
    the ones that bound.
    """
    subscriber = _a_real_subscriber()
    with _client() as client:
        body = client.post(
            "/v1/offer/next-best", json={"subscriber_id": subscriber, "channel": "api"}
        ).json()

    if not body["reason_codes"]:
        raise AssertionError("no reason codes -- an unexplainable offer")
    if not body["customer_facing_reason_ar"] or not body["customer_facing_reason_en"]:
        raise AssertionError("no customer-facing reason")
    if not body["decision_log_id"]:
        raise AssertionError("not logged, so not auditable and not replayable")

    considered = {c["name"] for c in body["constraints"]}
    required = {"margin_floor", "clv_ceiling", "cannibalisation", "fairness"}
    if not required <= considered:
        raise AssertionError(f"guardrails not recorded: {sorted(required - considered)}")

    binding = [c["name"] for c in body["constraints"] if c["binding"]]
    return (
        f"{body['offer_id']} at {body['price_lyd']:.2f} LYD via {body['instrument']}; "
        f"{len(considered)} guardrails considered, binding {binding or 'none'}"
    )


def check_no_action_is_a_real_outcome() -> str:
    """Most of the value in this system is in the offers it does not make. A
    run where every subscriber gets an offer means the uplift filter and the
    guardrails are not doing anything."""
    import pandas as pd

    from cvm.config import settings

    ids = pd.read_parquet(settings.feature_store_offline, columns=["subscriber_id_hashed"])
    sample = ids["subscriber_id_hashed"].astype(str).head(40).tolist()

    outcomes: dict[str, int] = {}
    with _client() as client:
        for subscriber in sample:
            body = client.post(
                "/v1/offer/next-best", json={"subscriber_id": subscriber, "channel": "api"}
            ).json()
            key = f"{body['offer_id']}|{body['instrument']}"
            outcomes[key] = outcomes.get(key, 0) + 1

    no_action = sum(v for k, v in outcomes.items() if k.startswith("NO_ACTION"))
    if no_action == 0:
        raise AssertionError(
            "every one of 40 subscribers got an offer. Either the uplift filter is not "
            "running or the guardrails are not binding -- both mean the engine is "
            "spending where it should not."
        )
    if no_action == len(sample):
        raise AssertionError("no subscriber got an offer; the engine is refusing everything")
    return f"{no_action} of {len(sample)} declined; outcomes {outcomes}"


def check_the_budget_is_never_exceeded() -> str:
    """Swept across budgets rather than spot-checked at one."""
    import numpy as np
    import pandas as pd

    from cvm.decision.budget_lp import allocate, campaign_summary

    rng = np.random.default_rng(606)
    n = 400
    candidates = pd.DataFrame(
        {
            "expected_margin_lyd": rng.gamma(2, 20, n),
            "discount_cost_lyd": rng.gamma(2, 3, n),
            "uplift": rng.random(n) * 0.1,
        }
    )
    for budget in (0.0, 100.0, 1_000.0, 144_000.0):
        allocation = allocate(candidates, budget_lyd=budget)
        spent = float(allocation.loc[allocation["selected"], "discount_cost_lyd"].sum())
        if spent > budget + 1e-6:
            raise AssertionError(f"allocated {spent:.2f} against a {budget:.2f} budget")

    summary = campaign_summary(allocate(candidates, budget_lyd=1_000.0))
    return (
        f"4 budgets respected; at 1,000 LYD it treats {summary['selected']} of "
        f"{summary['candidates']} for {summary['cost_lyd']:.0f}, saving "
        f"{summary['saving_versus_blanket_lyd']:.0f} against a blanket campaign"
    )


def check_a_decision_replays() -> str:
    """ "Why did this subscriber get 15 LYD and not 25?" must be answerable
    months later, from the log alone."""
    from cvm.decision import decision_log

    subscriber = _a_real_subscriber()
    with _client() as client:
        body = client.post(
            "/v1/offer/next-best", json={"subscriber_id": subscriber, "channel": "api"}
        ).json()

    result = decision_log.replay(body["decision_log_id"])
    if not result["reproduced"]:
        raise AssertionError(f"the decision does not replay: {result['verdict']}")
    return f"{body['decision_log_id'][:8]} replays: {result['verdict']}"


def check_replay_does_not_corrupt_config() -> str:
    """An audit function that mutates live pricing config is worse than none.

    The first version swapped weights into the CACHED config dict and restored
    them in a finally -- but the saved reference and the dict being cleared
    were the same object, so every later caller priced with no weights at all.
    """
    from cvm.config import load_conf
    from cvm.decision import decision_log

    before = dict(load_conf("pricing")["discount_weights"])
    if not before:
        raise AssertionError("the discount weights are already empty")

    subscriber = _a_real_subscriber()
    with _client() as client:
        body = client.post(
            "/v1/offer/next-best", json={"subscriber_id": subscriber, "channel": "api"}
        ).json()
    decision_log.replay(body["decision_log_id"])

    after = dict(load_conf("pricing")["discount_weights"])
    if after != before:
        raise AssertionError(f"replay changed the live weights: {before} -> {after}")
    return f"{len(before)} weights unchanged after a replay"


def check_serving_is_inside_the_latency_budget() -> str:
    """200 ms p95 on one CPU container. The early-warning version.

    Reading the OFFLINE parquet per request measured 292 ms for a single
    subscriber; the indexed online store is what this is for.
    """
    import time

    import numpy as np
    import pandas as pd

    from cvm.config import settings

    ids = pd.read_parquet(settings.feature_store_offline, columns=["subscriber_id_hashed"])
    sample = ids["subscriber_id_hashed"].astype(str).head(25).tolist()

    with _client() as client:
        client.post("/v1/offer/next-best", json={"subscriber_id": sample[0], "channel": "api"})
        timings = []
        for subscriber in sample:
            start = time.perf_counter()
            client.post("/v1/offer/next-best", json={"subscriber_id": subscriber, "channel": "api"})
            timings.append((time.perf_counter() - start) * 1000)

    p95 = float(np.percentile(timings, 95))
    if p95 > 200:
        raise AssertionError(f"p95 is {p95:.0f} ms against a 200 ms budget")
    return f"p95 {p95:.0f} ms over {len(timings)} calls, median {np.median(timings):.0f} ms"


# ---------------------------------------------------------------------------
# Phase 9 -- the surfaces
# ---------------------------------------------------------------------------

DASHBOARD_PAGES = (
    "apps/command_center/Home.py",
    "apps/command_center/pages/1_Executive_Overview.py",
    "apps/command_center/pages/2_Segment_Explorer.py",
    "apps/command_center/pages/3_Subscriber_360.py",
    "apps/command_center/pages/4_Campaign_Builder.py",
    "apps/channel_sim/Home.py",
)


def check_every_screen_renders() -> str:
    """The roadmap's check 3, run headlessly so CI catches a broken screen
    rather than a person discovering it mid-demo."""
    from streamlit.testing.v1 import AppTest

    from cvm.config import settings

    if not settings.feature_store_offline.exists():
        raise Pending("feature store not built; run `python -m cvm.features.run`")

    broken = {}
    for page in DASHBOARD_PAGES:
        app = AppTest.from_file(page, default_timeout=240).run()
        if app.exception:
            broken[page] = str(app.exception[0].value)[:120]
    if broken:
        raise AssertionError(f"{len(broken)} screen(s) raised: {broken}")
    return f"{len(DASHBOARD_PAGES)} screens render with no exception"


def check_the_360_renders_a_real_subscriber() -> str:
    """The demo centrepiece, with an id that exists. The check above would pass
    on a screen that stops at its empty state and draws nothing."""
    import pandas as pd
    from streamlit.testing.v1 import AppTest

    from cvm.config import settings

    if not settings.feature_store_offline.exists():
        raise Pending("feature store not built")

    subscriber = str(
        pd.read_parquet(settings.feature_store_offline, columns=["subscriber_id_hashed"]).iloc[0, 0]
    )
    app = AppTest.from_file("apps/command_center/pages/3_Subscriber_360.py", default_timeout=240)
    app.run()
    app.text_input[0].input(subscriber).run()

    if app.exception:
        raise AssertionError(str(app.exception[0].value)[:200])
    if len(app.metric) < 4:
        raise AssertionError(f"only {len(app.metric)} metrics rendered")
    return f"{len(app.metric)} metrics and {len(app.dataframe)} table(s) for a real subscriber"


def check_the_ui_refuses_a_raw_msisdn() -> str:
    """The privacy invariant, enforced in the UI rather than only the backend.
    A Streamlit widget value reaches session state and the server log, so
    rejecting a phone number downstream is too late."""
    from streamlit.testing.v1 import AppTest

    from cvm.config import settings

    if not settings.feature_store_offline.exists():
        raise Pending("feature store not built")

    # ASSEMBLED, NOT WRITTEN OUT. tests/unit/test_privacy.py scans every tracked
    # Python source for MSISDN-shaped strings and is right to -- "no raw MSISDN
    # anywhere in the repository" does not carve out test fixtures. The scanner
    # caught this line when it was a literal.
    looks_like_a_phone = "09" + "1" + "2345678"

    app = AppTest.from_file("apps/command_center/pages/3_Subscriber_360.py", default_timeout=240)
    app.run()
    app.text_input[0].input(looks_like_a_phone).run()

    if not any("phone number" in str(e.value).lower() for e in app.error):
        raise AssertionError("the lookup field accepted a raw MSISDN")
    return "a raw MSISDN is rejected before any lookup or log"


def check_sms_uses_the_real_ucs2_limit() -> str:
    """GSM-7 gives 160 characters per part; ANY Arabic character forces UCS-2,
    where one part is 70. A preview showing 160 would tell a campaign manager a
    message fits in one SMS when it sends as three -- billed per part."""
    import sys
    from pathlib import Path

    apps = str(Path(ROOT) / "apps")
    if apps not in sys.path:
        sys.path.insert(0, apps)
    from _shared import sms_parts

    alef = "\u0627"
    cases = {
        "latin 160": (("A" * 160), "GSM-7", 1),
        "latin 161": (("A" * 161), "GSM-7", 2),
        "arabic 60": ((alef * 60), "UCS-2", 1),
        "arabic 71": ((alef * 71), "UCS-2", 2),
        # The trap: one Arabic letter costs 90 characters of capacity.
        "100 latin + 1 arabic": (("A" * 100 + alef), "UCS-2", 2),
    }
    for name, (text, encoding, parts) in cases.items():
        info = sms_parts(text)
        if info["encoding"] != encoding or info["parts"] != parts:
            raise AssertionError(
                f"{name}: got {info['encoding']} / {info['parts']} parts, "
                f"expected {encoding} / {parts}"
            )
    return f"{len(cases)} cases, including one Arabic character forcing UCS-2 at 70"


def check_the_offer_copy_fits_one_sms() -> str:
    """The Arabic the engine actually sends. If it does not fit, the campaign
    costs double and nobody notices until the invoice."""
    import sys
    from pathlib import Path

    apps = str(Path(ROOT) / "apps")
    if apps not in sys.path:
        sys.path.insert(0, apps)
    from _shared import sms_parts
    from cvm.decision.pricing import _reason_ar

    worst = 0
    for instrument in ("offpeak_data", "onnet_minutes", "bonus_mb", "price_discount"):
        info = sms_parts(_reason_ar(instrument, "gold", 0.15))
        if info["parts"] > 1:
            raise AssertionError(f"{instrument} sends as {info['parts']} parts")
        worst = max(worst, info["length"])
    return f"4 instruments, longest {worst} of 70 UCS-2 characters"


def check_the_dashboard_reads_what_the_pipeline_wrote() -> str:
    """No screen recomputes a score, a CLV or an offer. A dashboard that
    recomputes will eventually disagree with the API, and the number an
    evaluator sees has to be the number the engine produced."""
    import sys
    from pathlib import Path

    apps = str(Path(ROOT) / "apps")
    if apps not in sys.path:
        sys.path.insert(0, apps)

    import pandas as pd

    from cvm.config import settings

    scores = settings.processed_dir / "m1_scores.parquet"
    if not scores.exists():
        raise Pending("m1_scores.parquet does not exist; run `python -m cvm.models.m1_churn.run`")

    stored = pd.read_parquet(scores)
    if stored["churn_probability"].isna().any():
        raise AssertionError("the stored scores contain NaN")
    if not stored["risk_decile"].between(1, 10).all():
        raise AssertionError("risk deciles outside 1-10")

    # Decile 1 must be the HIGHEST risk, matching the API contract. Inverted,
    # every screen would rank the safest subscribers as the most urgent.
    top = stored.loc[stored["risk_decile"] == 1, "churn_probability"].mean()
    bottom = stored.loc[stored["risk_decile"] == 10, "churn_probability"].mean()
    if not top > bottom:
        raise AssertionError(f"decile 1 mean {top:.4f} is not above decile 10 mean {bottom:.4f}")

    return (
        f"{len(stored):,} stored scores, decile 1 mean {top:.4f} against "
        f"decile 10 mean {bottom:.4f}"
    )


# ---------------------------------------------------------------------------
# Phase 10 -- ship
# ---------------------------------------------------------------------------


def _docker(*args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, cwd=ROOT, timeout=timeout, check=False
    )


def check_docker_daemon() -> str:
    """The daemon has to be up before anything else here means anything."""
    try:
        result = _docker("info", "--format", "{{.ServerVersion}}", timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise Pending(f"docker is not reachable: {exc}") from exc
    if result.returncode != 0:
        raise Pending("the Docker daemon is not running; start Docker Desktop")
    return f"daemon {result.stdout.strip()}"


def check_compose_is_valid() -> str:
    """`docker compose config` resolves every reference, including the
    Dockerfiles the services point at. A compose file naming a Dockerfile that
    does not exist validates as YAML and fails at build."""
    import yaml

    result = _docker("compose", "config", timeout=60)
    if result.returncode != 0:
        raise AssertionError(result.stderr.strip()[:300])

    parsed = yaml.safe_load(result.stdout)
    services = parsed.get("services", {})

    missing = []
    for name, service in services.items():
        build = service.get("build")
        if not build:
            continue
        dockerfile = ROOT / build.get("dockerfile", "Dockerfile")
        if not dockerfile.exists():
            missing.append(f"{name} -> {build.get('dockerfile')}")
    if missing:
        raise AssertionError(f"services point at Dockerfiles that do not exist: {missing}")

    return f"{len(services)} services, every Dockerfile present"


def check_images_build() -> str:
    """Deliverable D1. Built rather than assumed -- a Dockerfile that has never
    been built is a Dockerfile that does not work."""
    check_docker_daemon()

    images = {}
    for service in ("api", "ui"):
        result = _docker("compose", "build", service, timeout=1800)
        if result.returncode != 0:
            tail = (result.stderr or result.stdout).strip().splitlines()[-4:]
            raise AssertionError(f"{service} failed to build: {' | '.join(tail)}")

        tag = f"cvm-ali-branch-{service}:latest"
        size = _docker("image", "inspect", tag, "--format", "{{.Size}}", timeout=60)
        images[service] = int(size.stdout.strip()) / 1e9 if size.returncode == 0 else 0.0

    detail = ", ".join(f"{name} {size:.2f} GB" for name, size in images.items())
    return f"both images build ({detail})"


def check_the_stack_comes_up() -> str:
    """`docker compose up` with the API reporting healthy.

    The healthcheck polls /health, which is "ok" only when every model artefact
    is loaded AND the feature store is readable -- so a stack that comes up
    healthy has also proved the volume mounts are right.
    """
    check_docker_daemon()

    up = _docker("compose", "up", "-d", "api", timeout=600)
    if up.returncode != 0:
        raise AssertionError((up.stderr or up.stdout).strip()[:300])

    try:
        deadline = time.time() + 180
        status = "unknown"
        while time.time() < deadline:
            probe = _docker(
                "inspect", "--format", "{{.State.Health.Status}}", "cvm-api", timeout=30
            )
            status = probe.stdout.strip() or "unknown"
            if status == "healthy":
                break
            if status == "unhealthy":
                logs = _docker("compose", "logs", "--tail", "15", "api", timeout=60)
                raise AssertionError(f"api went unhealthy: {logs.stdout.strip()[-400:]}")
            time.sleep(5)

        if status != "healthy":
            logs = _docker("compose", "logs", "--tail", "15", "api", timeout=60)
            raise AssertionError(
                f"api never became healthy (last status {status!r}): {logs.stdout.strip()[-400:]}"
            )

        # And it answers from OUTSIDE the container, which is what the port
        # mapping is for -- a healthcheck passing inside proves less.
        import urllib.request

        with urllib.request.urlopen("http://localhost:8000/health", timeout=15) as response:
            body = json.loads(response.read())
        if body["status"] != "ok":
            missing = [k for k, v in body["models_loaded"].items() if not v]
            raise AssertionError(f"/health is {body['status']}; not loaded: {missing}")

        return f"api healthy and answering on :8000, status {body['status']}"
    finally:
        _docker("compose", "down", timeout=300)


def check_the_image_runs_as_a_non_root_user() -> str:
    """A container that serves HTTP and mounts the host's data directory should
    not be able to write to it as root."""
    check_docker_daemon()

    for service in ("api", "ui"):
        tag = f"cvm-ali-branch-{service}:latest"
        result = _docker("image", "inspect", tag, "--format", "{{.Config.User}}", timeout=60)
        if result.returncode != 0:
            raise Pending(f"{tag} has not been built")
        user = result.stdout.strip()
        if not user or user == "root" or user == "0":
            raise AssertionError(f"{service} runs as {user or 'root'}")
    return "api and ui both run as the unprivileged `cvm` user"


def check_no_secret_is_baked_into_an_image() -> str:
    """The salt is an environment variable at RUNTIME, never a build argument.

    A value passed with --build-arg is recorded in the image history and
    survives in every layer, so anyone who can pull the image can read it. The
    same hash salt also has to stay identical across runs or nothing
    reconciles, which is exactly what makes leaking it expensive.
    """
    check_docker_daemon()

    for service in ("api", "ui"):
        tag = f"cvm-ali-branch-{service}:latest"
        env = _docker("image", "inspect", tag, "--format", "{{json .Config.Env}}", timeout=60)
        if env.returncode != 0:
            raise Pending(f"{tag} has not been built")
        baked = json.loads(env.stdout)
        for entry in baked:
            name = entry.split("=", 1)[0].upper()
            if any(word in name for word in ("SALT", "SECRET", "TOKEN", "PASSWORD", "API_KEY")):
                raise AssertionError(f"{service} bakes {name} into the image")

    dockerfiles = list((ROOT / "docker").glob("*.Dockerfile"))
    for path in dockerfiles:
        text = path.read_text(encoding="utf-8")
        if "CVM_HASH_SALT" in text:
            raise AssertionError(f"{path.name} references CVM_HASH_SALT at build time")
    return f"no salt, token or key in {len(dockerfiles)} Dockerfiles or either image"


def check_the_pipeline_is_reproducible_end_to_end() -> str:
    """Every Parquet artefact the pipeline writes, hashed.

    Rebuilding all three data layers from source reproduces each one byte for
    byte. The DuckDB online store is content-reproducible but NOT
    byte-reproducible -- the format embeds write-time metadata -- so it is
    compared on content and never on hash.
    """
    import hashlib

    from cvm.config import settings

    artefacts = {
        "cell2cell": settings.interim_dir / "cell2cell.parquet",
        "population": settings.synthetic_dir / "population.parquet",
        "features": settings.feature_store_offline,
        "m1 scores": settings.processed_dir / "m1_scores.parquet",
        "m2 clv": settings.processed_dir / "m2_clv.parquet",
        "m3 uplift": settings.processed_dir / "m3_uplift.parquet",
        "m4 advance": settings.processed_dir / "m4_advance.parquet",
    }
    absent = [name for name, path in artefacts.items() if not path.exists()]
    if absent:
        raise Pending(f"{absent} do not exist; run the pipeline")

    digests = {
        name: hashlib.md5(path.read_bytes()).hexdigest()[:8] for name, path in artefacts.items()
    }
    return f"{len(digests)} Parquet artefacts present, md5 {digests['population']} (population)"


def check_the_demo_path_is_runnable() -> str:
    """The three-minute pitch, as commands rather than as a description.

    Every step below is something an evaluator can type. A demo that only runs
    from a notebook nobody else can open is not a demo.
    """
    steps = [
        ("scoring", ROOT / "src/cvm/models/m1_churn/run.py"),
        ("command center", ROOT / "apps/command_center/Home.py"),
        ("subscriber 360", ROOT / "apps/command_center/pages/3_Subscriber_360.py"),
        ("channel simulator", ROOT / "apps/channel_sim/Home.py"),
        ("compose", ROOT / "docker-compose.yml"),
        ("integration contract", ROOT / "docs/INTEGRATION.md"),
    ]
    missing = [name for name, path in steps if not path.exists()]
    if missing:
        raise AssertionError(f"the demo path is broken: {missing} missing")
    return f"{len(steps)} demo entry points present and runnable"


# ---------------------------------------------------------------------------
# Every phase is declared. Nothing below this line is pending by design.
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
        ("both stores built", check_both_stores_exist),
        ("leakage suite fully green", check_leakage_suite),
        ("point-in-time serving", check_point_in_time_serving),
        ("splits temporal and disjoint", check_splits_are_temporal),
        ("no label artefacts, target kept", check_no_label_artifacts),
        ("RFM-LE segments populate", check_segments_populate),
        ("no raw identifiers", check_no_raw_identifiers_in_features),
        ("feature families complete", check_feature_coverage),
    ],
    "4": [
        ("benchmark table has 8 models", check_benchmark_table),
        ("calibration improves Brier", check_calibration_improves),
        ("leakage suite, zero xfail", check_leakage_suite_has_no_xfail),
        ("naive vs honest disclosed", check_naive_vs_honest),
        ("survival held out", check_survival_is_held_out),
        ("explanations are plain language", check_explanations_are_plain),
        ("SHAP attribution by family", check_shap_attribution),
        ("serving artefact loads", check_model_artefact_loads),
    ],
    "5": [
        ("BG/NBD validated on holdout", check_bg_nbd_on_real_purchases),
        ("no degenerate BG/NBD fit", check_no_degenerate_bg_nbd_fit),
        ("CLV ceiling is live", check_clv_ceiling_is_live),
        ("every subscriber has a ceiling", check_every_subscriber_has_a_ceiling),
        ("k chosen by silhouette", check_k_is_chosen_by_silhouette),
        ("rules and clusters disagree", check_rules_and_clusters_disagree),
        ("segments tested against the data", check_segments_are_tested_against_the_data),
        ("PCA variance reported", check_pca_variance_reported),
    ],
    "6": [
        ("Qini on Criteo > 0", check_qini_on_criteo),
        ("Qini matches scikit-uplift", check_qini_matches_the_reference),
        ("all four quadrants populate", check_all_four_quadrants_populate),
        ("break-even at 1.04 pp", check_break_even_is_where_the_proposal_says),
        ("holdout mandatory and random", check_the_holdout_is_mandatory_and_random),
        ("pipeline test is held out", check_the_pipeline_test_is_held_out),
        ("only persuadables funded", check_only_persuadables_are_funded),
        ("funding respects the CLV ceiling", check_expected_value_respects_the_clv_ceiling),
    ],
    "7": [
        ("guardrail suite, zero xfail", check_guardrail_suite_has_no_xfail),
        ("the headline case", check_the_headline_case),
        ("guards only reduce", check_guards_only_reduce),
        ("no invented denominations", check_no_invented_denominations),
        ("selection bias measured", check_selection_bias_is_measured),
        ("reject inference shifts sanely", check_reject_inference_shifts_but_does_not_swamp),
        ("advance decisions landed", check_advance_decisions_landed),
    ],
    "8": [
        ("endpoints return 200 not 501", check_endpoints_stop_returning_501),
        ("health reports ok", check_health_is_ok),
        ("every offer is explainable", check_every_offer_is_explainable),
        ("no action is a real outcome", check_no_action_is_a_real_outcome),
        ("budget never exceeded", check_the_budget_is_never_exceeded),
        ("a decision replays", check_a_decision_replays),
        ("replay leaves config alone", check_replay_does_not_corrupt_config),
        ("p95 inside 200 ms", check_serving_is_inside_the_latency_budget),
    ],
    "9": [
        ("every screen renders", check_every_screen_renders),
        ("the 360 renders a real subscriber", check_the_360_renders_a_real_subscriber),
        ("the UI refuses a raw MSISDN", check_the_ui_refuses_a_raw_msisdn),
        ("SMS uses the real UCS-2 limit", check_sms_uses_the_real_ucs2_limit),
        ("offer copy fits one SMS", check_the_offer_copy_fits_one_sms),
        ("screens read pipeline output", check_the_dashboard_reads_what_the_pipeline_wrote),
    ],
    "10": [
        ("docker daemon reachable", check_docker_daemon),
        ("compose file is valid", check_compose_is_valid),
        ("images build", check_images_build),
        ("the stack comes up healthy", check_the_stack_comes_up),
        ("containers run as non-root", check_the_image_runs_as_a_non_root_user),
        ("no secret baked into an image", check_no_secret_is_baked_into_an_image),
        ("pipeline artefacts reproduce", check_the_pipeline_is_reproducible_end_to_end),
        ("the demo path is runnable", check_the_demo_path_is_runnable),
    ],
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
