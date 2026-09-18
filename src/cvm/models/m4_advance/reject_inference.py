"""Reject inference.  Owner: E2

Repayment is only observed for subscribers who were actually granted an
advance, which is textbook selection bias: the training population is filtered
by the incumbent's 12-month gate and by whatever else drove uptake.

Left uncorrected, the model learns "everyone repays" because the risky
applicants are invisible. The report documents the bias explicitly and this
module applies a fuzzy-augmentation correction. Also stated in the model card.
"""

from __future__ import annotations

import pandas as pd


def fuzzy_augmentation(
    accepted: pd.DataFrame, rejected: pd.DataFrame, model
) -> pd.DataFrame:
    """Augment the training set with probability-weighted rejected applicants."""
    raise NotImplementedError("TODO(E2)")


def quantify_bias(accepted: pd.DataFrame, rejected: pd.DataFrame) -> dict[str, float]:
    """Compare covariate distributions. Goes straight into the model card."""
    raise NotImplementedError("TODO(E2)")