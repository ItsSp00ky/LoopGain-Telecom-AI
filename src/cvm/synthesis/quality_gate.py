"""SDMetrics quality gate. Above threshold, the generator is REJECTED.

Three gates, all of which must pass:

    KS-complement on continuous marginals   >= 0.85
    pairwise correlation delta              <= 0.10
    discriminator detection AUC             <= 0.65

The third is the one worth a slide: a LightGBM classifier trained to separate
real from synthetic should not manage better than 0.65 AUC. We evaluate our GAN
with an adversarial test -- the same principle that trains it.

This also guards against the biggest risk in the register: generated data that
is too clean makes models look unrealistically good.

WHY THREE AND NOT ONE. They fail in different directions, and any one alone is
gameable. Matching every marginal while destroying the correlation structure
passes KS and fails the delta. Copying the real rows outright passes both and
fails nothing -- which is why the detector matters: a memorising generator is
trivially separable from its own training data only if you hold rows back, so
the detector is trained on a split. Between them the three cover "right shape",
"right relationships" and "not obviously fake".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

from cvm.config import load_conf, settings

log = logging.getLogger(__name__)


def _conf() -> dict:
    return load_conf("data")["synthesis"]["quality_gate"]


def _numeric_columns(real: pd.DataFrame, synthetic: pd.DataFrame) -> list[str]:
    shared = [c for c in real.columns if c in synthetic.columns]
    return [c for c in shared if pd.api.types.is_numeric_dtype(real[c])]


@dataclass(frozen=True)
class GateResult:
    ks_complement: float
    correlation_delta: float
    detection_auc: float
    passed: bool

    def summary(self) -> str:
        conf = _conf()
        rows = [
            ("KS-complement", self.ks_complement, ">=", conf["ks_complement_min"]),
            (
                "correlation delta",
                self.correlation_delta,
                "<=",
                conf["pairwise_correlation_delta_max"],
            ),
            ("detection AUC", self.detection_auc, "<=", conf["discriminator_detection_auc_max"]),
        ]
        lines = [f"{'METRIC':<20}{'VALUE':>9}  {'':<3}{'THRESHOLD':>10}  RESULT"]
        for name, value, operator, threshold in rows:
            ok = value >= threshold if operator == ">=" else value <= threshold
            lines.append(
                f"{name:<20}{value:>9.4f}  {operator:<3}{threshold:>10.2f}  "
                f"{'pass' if ok else 'FAIL'}"
            )
        verdict = "GATE PASSED" if self.passed else "GATE FAILED -- generator rejected"
        return "\n".join([*lines, "", verdict])


def ks_complement(real: pd.DataFrame, synthetic: pd.DataFrame) -> float:
    """Mean 1 - KS statistic across shared numeric marginals. Higher is better.

    One minus the Kolmogorov-Smirnov statistic, so 1.0 is an identical
    distribution and 0.0 is no overlap. Averaged across columns, which means a
    single badly-generated column can hide behind eighty good ones -- so the
    worst column is logged alongside the mean.
    """
    from scipy.stats import ks_2samp

    columns = _numeric_columns(real, synthetic)
    if not columns:
        raise ValueError("no shared numeric columns to compare")

    scores: dict[str, float] = {}
    for column in columns:
        left = real[column].dropna()
        right = synthetic[column].dropna()
        if left.empty or right.empty:
            continue
        scores[column] = 1.0 - float(ks_2samp(left, right).statistic)

    worst = min(scores, key=scores.get)  # type: ignore[arg-type]
    mean = float(np.mean(list(scores.values())))
    log.info(
        "gate ks_complement: mean %.4f over %d columns, worst %s at %.4f",
        mean,
        len(scores),
        worst,
        scores[worst],
    )
    return mean


def correlation_delta(real: pd.DataFrame, synthetic: pd.DataFrame) -> float:
    """Mean absolute difference between the two correlation matrices.

    Spearman rather than Pearson: several of these fields are heavy-tailed
    ratios, and a Pearson correlation on a lognormal column is mostly a
    statement about its outliers. Rank correlation is what the generator can
    reasonably be asked to preserve.

    Only the upper triangle, so each pair counts once and the diagonal of ones
    does not dilute the average toward zero.
    """
    columns = _numeric_columns(real, synthetic)
    if len(columns) < 2:
        raise ValueError("need at least two numeric columns for a correlation delta")

    left = real[columns].corr(method="spearman").to_numpy()
    right = synthetic[columns].corr(method="spearman").to_numpy()
    upper = np.triu_indices_from(left, k=1)
    difference = np.abs(left[upper] - right[upper])
    difference = difference[np.isfinite(difference)]

    mean = float(difference.mean())
    log.info(
        "gate correlation_delta: mean %.4f over %d pairs, worst %.4f",
        mean,
        difference.size,
        float(difference.max()),
    )
    return mean


def detection_auc(real: pd.DataFrame, synthetic: pd.DataFrame) -> float:
    """Train LightGBM to tell real from synthetic. Lower is better.

    0.50 means indistinguishable; 1.00 means trivially separable. Evaluated on
    a held-out split, because a detector scored on its own training rows would
    report a memorising generator as excellent.

    This is the gate that catches what the other two cannot. A generator can
    match every marginal and every pairwise correlation and still place its
    rows somewhere no real subscriber lives -- in a corner of the joint
    distribution the margins do not describe. A tree ensemble finds that
    immediately.
    """
    from lightgbm import LGBMClassifier
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import train_test_split

    columns = _numeric_columns(real, synthetic)
    if not columns:
        raise ValueError("no shared numeric columns to detect on")

    # Balanced, so the AUC is not flattered by a size imbalance between the
    # real sample and the generated population.
    size = min(len(real), len(synthetic))
    rng = np.random.default_rng(settings.random_seed)
    left = real[columns].iloc[rng.choice(len(real), size, replace=False)]
    right = synthetic[columns].iloc[rng.choice(len(synthetic), size, replace=False)]

    features = pd.concat([left, right], ignore_index=True)
    labels = np.r_[np.zeros(size), np.ones(size)]

    x_train, x_test, y_train, y_test = train_test_split(
        features, labels, test_size=0.3, random_state=settings.random_seed, stratify=labels
    )
    detector = LGBMClassifier(
        n_estimators=200,
        learning_rate=0.05,
        num_leaves=31,
        verbose=-1,
        random_state=settings.random_seed,
    )
    detector.fit(x_train, y_train)
    auc = float(roc_auc_score(y_test, detector.predict_proba(x_test)[:, 1]))

    giveaways = (
        pd.Series(detector.feature_importances_, index=columns).sort_values(ascending=False).head(3)
    )
    log.info(
        "gate detection_auc: %.4f on %d held-out rows; most separable columns %s",
        auc,
        len(x_test),
        {k: int(v) for k, v in giveaways.items()},
    )
    return auc


def run_gate(real: pd.DataFrame, synthetic: pd.DataFrame) -> GateResult:
    """Run all three gates. Callers must treat a failure as fatal.

    Compares the generator's output against the generator's *own training
    data*, and nothing else. Comparing against the overlaid population would
    measure the overlays, which are business rules we wrote deliberately and
    which a detector should be able to spot.
    """
    conf = _conf()
    if not conf.get("enabled", True):
        log.warning("quality gate is DISABLED in conf/data.yaml -- returning a vacuous pass")
        return GateResult(1.0, 0.0, 0.5, True)

    ks = ks_complement(real, synthetic)
    delta = correlation_delta(real, synthetic)
    auc = detection_auc(real, synthetic)

    passed = (
        ks >= conf["ks_complement_min"]
        and delta <= conf["pairwise_correlation_delta_max"]
        and auc <= conf["discriminator_detection_auc_max"]
    )
    result = GateResult(ks, delta, auc, passed)
    log.info("\n%s", result.summary())
    return result


def enforce(result: GateResult) -> None:
    """Raise unless the gate passed. The pipeline must call this.

    Separate from `run_gate` so the generator comparison can score a failing
    candidate without aborting -- but the pipeline itself has no such licence,
    and `fail_build_on_breach` in conf/data.yaml is true for that reason.
    """
    if result.passed:
        return
    if not _conf().get("fail_build_on_breach", True):
        log.warning("gate FAILED but fail_build_on_breach is false; continuing under protest")
        return
    raise ValueError(
        "Quality gate failed -- the generated population is not usable.\n\n"
        + result.summary()
        + "\n\nA failing gate is not a warning. If detection AUC is above the "
        "threshold the population is distinguishable from real data, and every "
        "metric measured on it downstream describes something a discriminator "
        "can already tell is fake. Retrain, or fall back to the copula."
    )
