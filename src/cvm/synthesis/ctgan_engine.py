"""Adversarial fit: CTGAN (primary), TVAE (challenger), Copula (baseline).

Comparing all three is itself a reportable experiment (deliverable D2), not
scaffolding for the one we keep.
"""

from __future__ import annotations

import pandas as pd


def fit_ctgan(real: pd.DataFrame, **kwargs):
    """Fit the conditional tabular GAN. Primary generator."""
    raise NotImplementedError("TODO(E1): sdv.single_table.CTGANSynthesizer")


def fit_tvae(real: pd.DataFrame, **kwargs):
    """Fit the tabular VAE. Challenger."""
    raise NotImplementedError("TODO(E1)")


def fit_copula(real: pd.DataFrame, **kwargs):
    """Fit a Gaussian copula. Classical baseline -- fast, and sometimes wins."""
    raise NotImplementedError("TODO(E1)")


def sample(model, n: int, seed: int | None = None) -> pd.DataFrame:
    """Draw n synthetic subscribers. Seeded: the population is reproducible."""
    raise NotImplementedError("TODO(E1)")