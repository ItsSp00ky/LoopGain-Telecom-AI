"""Reject inference.  Owner: E2

Repayment is only observed for subscribers who were actually granted an
advance, which is textbook selection bias: the training population is filtered
by the incumbent's 12-month gate and by whatever else drove uptake.

Left uncorrected, the model learns "everyone repays" because the risky
applicants are invisible. The report documents the bias explicitly and this
module applies a fuzzy-augmentation correction. Also stated in the model card.

THE BIAS IS SHARPER HERE THAN IN ORDINARY CREDIT, and the reason is worth
stating plainly. A bank's accept/reject gate is a risk filter, so the observed
population is the SAFER tail and the correction pulls the estimate down.
Almadar's gate is `balance <= 0.5 LYD` -- it selects on being broke. The
observed population is filtered toward financial stress, not away from it, so
the direction of the bias is not the textbook one and cannot be assumed. It has
to be measured, which is what `quantify_bias` is for.

WHAT FUZZY AUGMENTATION ACTUALLY DOES, since the name oversells it. Each
rejected applicant enters the training set TWICE: once labelled repaid with
weight p, once labelled defaulted with weight 1-p, where p comes from the
accepts-only model. It is not new information -- it cannot be, the outcome was
never observed -- it is a way of stopping the model from being confident about
a region of feature space it has no data in. That is a real benefit and a
modest one, and it is not a substitute for a randomised grant policy.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from cvm.config import load_conf

log = logging.getLogger(__name__)

WEIGHT = "sample_weight"
LABEL = "repaid_by_next_recharge"


def _conf() -> dict:
    return load_conf("advance")["safety_guards"]["reject_inference"]


def fuzzy_augmentation(accepted: pd.DataFrame, rejected: pd.DataFrame, model) -> pd.DataFrame:
    """Augment the training set with probability-weighted rejected applicants.

    Returns one frame carrying `sample_weight`: the accepted rows at weight
    1.0, and each rejected row duplicated at weights p and 1-p.

    Refuses to run when the config has it switched off, because the same config
    marks it mandatory and `tests/guardrails/` asserts that. A correction that
    can be quietly disabled is not a correction.
    """
    conf = _conf()
    if not conf.get("enabled", True):
        raise ValueError(
            "reject_inference is disabled in conf/advance.yaml, where it is also "
            "documented as mandatory. The gate is balance-based, so the observed "
            "population is non-random by construction and the uncorrected model "
            "learns that almost everyone repays."
        )
    if conf.get("method") != "fuzzy_augmentation":
        raise ValueError(f"conf asks for {conf.get('method')!r}; only fuzzy_augmentation exists")

    if LABEL not in accepted.columns:
        raise KeyError(f"{LABEL} absent from the accepted rows; nothing to augment")
    if rejected.empty:
        log.warning("no rejected applicants supplied; returning the accepted rows unchanged")
        return accepted.assign(**{WEIGHT: 1.0})

    features = [c for c in accepted.columns if c not in (LABEL, WEIGHT)]
    probability = np.clip(np.asarray(model.predict_proba(rejected[features])[:, 1]), 0.0, 1.0)

    repaid = rejected.copy()
    repaid[LABEL] = 1
    repaid[WEIGHT] = probability

    defaulted = rejected.copy()
    defaulted[LABEL] = 0
    defaulted[WEIGHT] = 1.0 - probability

    augmented = pd.concat([accepted.assign(**{WEIGHT: 1.0}), repaid, defaulted], ignore_index=True)

    log.info(
        "fuzzy augmentation: %d accepted + %d rejected x2 = %d weighted rows; "
        "inferred repayment rate among rejects %.4f against %.4f observed among accepts",
        len(accepted),
        len(rejected),
        len(augmented),
        float(probability.mean()),
        float(accepted[LABEL].mean()),
    )
    return augmented


def quantify_bias(accepted: pd.DataFrame, rejected: pd.DataFrame) -> dict[str, float]:
    """Compare covariate distributions. Goes straight into the model card.

    Standardised mean difference per feature, because it is unit-free and
    comparable across columns that are measured in days, LYD and counts. The
    conventional reading is that anything above 0.1 is a meaningful imbalance
    and above 0.25 is severe.

    The SIGN matters as much as the size and is reported per feature rather
    than only as a magnitude: it says which direction the observed population
    is skewed, and for this operator that direction is the surprising part.
    """
    shared = [
        c
        for c in accepted.columns
        if c in rejected.columns
        and c not in (LABEL, WEIGHT)
        and pd.api.types.is_numeric_dtype(accepted[c])
    ]
    if not shared:
        raise ValueError("no shared numeric columns; the two populations cannot be compared")

    differences: dict[str, float] = {}
    for column in shared:
        a, r = accepted[column].dropna(), rejected[column].dropna()
        if a.empty or r.empty:
            continue
        pooled = np.sqrt((a.var() + r.var()) / 2.0)
        if pooled == 0 or not np.isfinite(pooled):
            continue
        differences[column] = float((a.mean() - r.mean()) / pooled)

    if not differences:
        raise ValueError("no comparable columns after dropping constants and empties")

    magnitudes = {k: abs(v) for k, v in differences.items()}
    worst = max(magnitudes, key=magnitudes.get)
    severe = [k for k, v in magnitudes.items() if v > 0.25]

    summary = {
        "n_accepted": len(accepted),
        "n_rejected": len(rejected),
        "accepted_share": len(accepted) / (len(accepted) + len(rejected)),
        "features_compared": len(differences),
        "max_abs_smd": magnitudes[worst],
        "max_abs_smd_feature": worst,
        "mean_abs_smd": float(np.mean(list(magnitudes.values()))),
        "features_above_0_25": len(severe),
        "standardised_mean_differences": differences,
    }
    log.info(
        "selection bias: %d accepted (%.1f%%) against %d never-borrowed; worst imbalance "
        "%s at SMD %+.3f, %d features above 0.25 -- %s",
        len(accepted),
        100 * summary["accepted_share"],
        len(rejected),
        worst,
        differences[worst],
        len(severe),
        (
            "the observed population is NOT a random sample and the model card says so"
            if summary["max_abs_smd"] > 0.1
            else "the two populations are close, which is worth checking rather than assuming"
        ),
    )
    return summary
