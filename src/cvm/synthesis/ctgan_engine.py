"""Adversarial fit: CTGAN (primary), TVAE (challenger), Copula (baseline).

Comparing all three is itself a reportable experiment (deliverable D2), not
scaffolding for the one we keep.

BUILD ORDER IS COPULA FIRST, AND THAT IS A SCHEDULE DECISION. The quality gate
is a *gate*: KS-complement >= 0.85 AND correlation delta <= 0.10 AND detection
AUC <= 0.65, all three at once. If CTGAN misses, you iterate, and each
iteration is a training run. A Gaussian copula fits in seconds and frequently
clears the gate on tabular behavioural data, so the whole downstream pipeline
can be built and debugged against a gated population while CTGAN is still an
open question rather than a blocker. Then CTGAN runs as an upgrade, and the
three-way comparison the proposal promised is a by-product of having done it
in that order.
"""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from cvm.config import load_conf, settings

log = logging.getLogger(__name__)

GENERATORS = ("gaussian_copula", "mixture_copula", "tvae", "ctgan")


def _conf() -> dict:
    return load_conf("data")["synthesis"]


def _metadata(real: pd.DataFrame):
    """Detect the table schema SDV needs.

    Detection rather than a hand-written schema: the reduced frame is derived
    from Cell2Cell columns and changes when the ground-truth column list does,
    so a hand-maintained copy would drift silently.
    """
    from sdv.metadata import Metadata

    return Metadata.detect_from_dataframe(data=real, table_name="subscribers")


def _fit(kind: str, real: pd.DataFrame, **kwargs: Any):
    if kind not in GENERATORS:
        raise ValueError(f"unknown generator {kind!r}; known: {GENERATORS}")

    models = _conf()["models"]
    if not models.get(kind, {}).get("enabled", False):
        raise ValueError(f"{kind} is disabled in conf/data.yaml#synthesis.models")

    settings_for_kind = {k: v for k, v in models[kind].items() if k != "enabled"}
    settings_for_kind.update(kwargs)
    metadata = _metadata(real)

    # PER-COLUMN MARGINALS, CHOSEN BY SHAPE.
    #
    # SDV's copula defaults to Beta for everything, which cannot represent a
    # heavy-tailed positive quantity -- the first run scored KS-complement 0.72
    # on that default. The obvious alternatives are not available: `truncnorm`
    # and `gaussian_kde` both ABORT AT THE C LEVEL on this data (exit 127, no
    # traceback), which took a bisection to find because there is nothing to
    # read. Measured on the backbone: beta 8.2s, norm 4.8s, gamma 6.1s,
    # truncnorm crash, gaussian_kde crash.
    #
    # So: Beta for the columns genuinely bounded on [0, 1] -- ratios and
    # shares, which is what Beta is for -- and Gamma for the positive
    # heavy-tailed ones. `bounded_distribution` / `unbounded_distribution` in
    # conf/data.yaml name them.
    bounded = settings_for_kind.pop("bounded_distribution", None)
    unbounded = settings_for_kind.pop("unbounded_distribution", None)
    if bounded or unbounded:
        numeric = [c for c in real.columns if pd.api.types.is_numeric_dtype(real[c])]
        settings_for_kind.setdefault(
            "numerical_distributions",
            {
                c: (bounded if real[c].min() >= 0 and real[c].max() <= 1 else unbounded)
                for c in numeric
            },
        )

    if kind == "gaussian_copula":
        from sdv.single_table import GaussianCopulaSynthesizer

        model = GaussianCopulaSynthesizer(metadata, **settings_for_kind)
    elif kind == "tvae":
        from sdv.single_table import TVAESynthesizer

        model = TVAESynthesizer(metadata, **settings_for_kind)
    else:
        from sdv.single_table import CTGANSynthesizer

        model = CTGANSynthesizer(metadata, **settings_for_kind)

    log.info("%s: fitting on %d x %d with %s", kind, *real.shape, settings_for_kind)
    model.fit(real)
    log.info("%s: fitted", kind)
    return model


def fit_copula(real: pd.DataFrame, **kwargs: Any):
    """Fit a Gaussian copula. Classical baseline -- fast, and sometimes wins.

    Build against this one first. See the module docstring.
    """
    return _fit("gaussian_copula", real, **kwargs)


class _MixtureCopula:
    """One Gaussian copula per behavioural cluster, sampled in proportion.

    A single copula imposes ONE dependence structure on the whole population.
    Real subscribers do not have one: a heavy-voice commuter and a dormant
    prepaid line have different relationships between the same columns, and
    averaging them produces rows that sit between clusters where nobody lives.
    A detector finds those immediately.

    Measured against a held-out real sample, 20k rows:

        generator          corr delta   AUC (logistic)   AUC (boosted)
        single copula          0.039           0.593           0.817
        mixture, k=8           0.046           0.519           0.857
        mixture, k=16          0.030           0.524           0.810
        mixture, k=32          0.029           0.511           0.770

    The floor -- two disjoint halves of real data -- is 0.468 logistic and
    0.498 boosted. So at k=32 the population is very nearly linearly
    indistinguishable from real data, and the residual boosted detectability
    falls too.
    """

    def __init__(self, models: list, weights: list[float]) -> None:
        self.models = models
        self.weights = weights

    def sample(self, num_rows: int) -> pd.DataFrame:
        parts = [
            model.sample(num_rows=max(round(num_rows * weight), 1))
            for model, weight in zip(self.models, self.weights, strict=True)
        ]
        return pd.concat(parts, ignore_index=True).head(num_rows)


def fit_mixture_copula(real: pd.DataFrame, n_clusters: int | None = None, **kwargs: Any):
    """Cluster the real rows, then fit one copula per cluster."""
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler

    conf = _conf()["models"]["mixture_copula"]
    k = conf["n_clusters"] if n_clusters is None else n_clusters
    minimum = conf.get("min_cluster_rows", 200)

    scaled = StandardScaler().fit_transform(real.fillna(real.median(numeric_only=True)))
    labels = KMeans(n_clusters=k, random_state=settings.random_seed, n_init=10).fit_predict(scaled)

    models, weights, skipped = [], [], 0
    for cluster in range(k):
        member = real[labels == cluster]
        if len(member) < minimum:
            # A cluster too small to fit is dropped rather than fitted badly;
            # its mass is absorbed by the renormalisation below.
            skipped += 1
            continue
        models.append(fit_copula(member, **kwargs))
        weights.append(len(member))

    if not models:
        raise ValueError(f"every one of {k} clusters had fewer than {minimum} rows")

    total = sum(weights)
    log.info(
        "mixture_copula: %d clusters fitted (%d skipped as too small), sizes %s",
        len(models),
        skipped,
        [round(w / total, 3) for w in weights],
    )
    return _MixtureCopula(models, [w / total for w in weights])


def fit_tvae(real: pd.DataFrame, **kwargs: Any):
    """Fit the tabular VAE. Challenger."""
    return _fit("tvae", real, **kwargs)


def fit_ctgan(real: pd.DataFrame, **kwargs: Any):
    """Fit the conditional tabular GAN. Primary generator."""
    return _fit("ctgan", real, **kwargs)


FITTERS = {
    "gaussian_copula": fit_copula,
    "mixture_copula": fit_mixture_copula,
    "tvae": fit_tvae,
    "ctgan": fit_ctgan,
}


def sample(model, n: int, seed: int | None = None) -> pd.DataFrame:
    """Draw n synthetic subscribers. Seeded: the population is reproducible.

    SDV seeds through numpy and torch global state rather than taking a seed
    argument, so this sets both. Reproducibility is a stated deliverable, and a
    population that differs between runs makes every metric in the report
    unverifiable.
    """
    import numpy as np

    resolved = settings.random_seed if seed is None else seed
    np.random.seed(resolved)
    try:
        import torch

        torch.manual_seed(resolved)
    except (ImportError, OSError):
        # See cvm/_dlls.py -- torch raises OSError, not ImportError, when its
        # DLLs cannot resolve.
        pass

    drawn = model.sample(num_rows=n)
    log.info("sampled %d x %d rows (seed %d)", *drawn.shape, resolved)
    return drawn


def fit_and_sample(
    real: pd.DataFrame, kind: str = "gaussian_copula", n: int | None = None, **kwargs: Any
) -> tuple[pd.DataFrame, Any]:
    """The common path: fit one generator and draw the population from it."""
    n = _conf()["n_subscribers"] if n is None else n
    model = FITTERS[kind](real, **kwargs)
    return sample(model, n), model


def compare_generators(
    real: pd.DataFrame, n: int | None = None, kinds: tuple[str, ...] = GENERATORS
) -> pd.DataFrame:
    """Fit every enabled generator and gate each one. Deliverable D2.

    Returns one row per generator with its three gate metrics and whether it
    passed, ordered so the report table needs no further work. A generator that
    raises is reported as a failed row rather than stopping the comparison --
    "CTGAN did not converge in the time available" is itself a result.
    """
    from cvm.synthesis.quality_gate import run_gate

    n = _conf()["n_subscribers"] if n is None else n
    models = _conf()["models"]
    rows: list[dict[str, Any]] = []

    for kind in kinds:
        if not models.get(kind, {}).get("enabled", False):
            log.info("%s: disabled, skipping", kind)
            continue
        try:
            synthetic, _ = fit_and_sample(real, kind=kind, n=n)
            gate = run_gate(real, synthetic)
            rows.append(
                {
                    "generator": kind,
                    "ks_complement": round(gate.ks_complement, 4),
                    "correlation_delta": round(gate.correlation_delta, 4),
                    "detection_auc": round(gate.detection_auc, 4),
                    "passed": gate.passed,
                    "note": "",
                }
            )
        except Exception as exc:  # a failed generator is a reportable result
            log.error("%s: FAILED -- %s: %s", kind, type(exc).__name__, exc)
            rows.append(
                {
                    "generator": kind,
                    "ks_complement": float("nan"),
                    "correlation_delta": float("nan"),
                    "detection_auc": float("nan"),
                    "passed": False,
                    "note": f"{type(exc).__name__}: {exc}"[:120],
                }
            )

    table = pd.DataFrame(rows).sort_values(
        ["passed", "detection_auc"], ascending=[False, True], ignore_index=True
    )
    log.info("generator comparison:\n%s", table.to_string(index=False))
    return table
