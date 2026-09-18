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
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class GateResult:
    ks_complement: float
    correlation_delta: float
    detection_auc: float
    passed: bool

    def summary(self) -> str:
        raise NotImplementedError("TODO(E1)")


def ks_complement(real: pd.DataFrame, synthetic: pd.DataFrame) -> float:
    raise NotImplementedError("TODO(E1)")


def correlation_delta(real: pd.DataFrame, synthetic: pd.DataFrame) -> float:
    raise NotImplementedError("TODO(E1)")


def detection_auc(real: pd.DataFrame, synthetic: pd.DataFrame) -> float:
    """Train LightGBM to tell real from synthetic. Lower is better."""
    raise NotImplementedError("TODO(E1)")


def run_gate(real: pd.DataFrame, synthetic: pd.DataFrame) -> GateResult:
    """Run all three gates. Callers must treat a failure as fatal."""
    raise NotImplementedError("TODO(E1)")