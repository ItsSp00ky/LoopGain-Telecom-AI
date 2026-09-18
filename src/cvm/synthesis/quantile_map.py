"""Map real monetary fields onto the Libyan scale by quantile.

The Iranian `Charge Amount` field is ordinal 0-9 and Cell2Cell's revenue is in
US dollars. Mapping by quantile onto the LYD recharge ladder means a
90th-percentile spender lands on a 100 LYD card rather than a 5 LYD one --
preserving the rank structure the generator learned while changing the units to
ones a Libyan evaluator recognises.

QUANTILE, NOT LINEAR RESCALING. A linear map would preserve the shape of a
distribution measured in another currency in another market, which is a shape
we have no reason to believe. The rank is the transferable part: whoever was in
the top decile of spend there should be in the top decile here. What the ladder
supplies is the *support* -- the five values Almadar actually prints.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from cvm.config import load_conf

log = logging.getLogger(__name__)


def recharge_ladder() -> tuple[int, ...]:
    """Almadar's confirmed denominations, from conf/market.yaml.

    Read rather than hardcoded. An earlier version of this module carried
    ``(5, 10, 15, 20, 25, 50, 100)``, which contains three denominations the
    operator does not sell -- and a generator that invents a 15 LYD card is
    generating a market that does not exist.
    """
    ladder = tuple(load_conf("market")["recharge"]["denominations_lyd"])
    mirror = tuple(load_conf("data")["synthesis"]["quantile_mapping"]["recharge_denominations_lyd"])
    if ladder != mirror:
        raise ValueError(
            f"conf/market.yaml has {ladder} but conf/data.yaml has {mirror}. "
            "These mirror each other by design; they have drifted."
        )
    return ladder


def ladder_weights() -> np.ndarray:
    """Popularity weights for the ladder, normalised.

    An ASSUMPTION, and labelled as one in conf/market.yaml: the ladder is
    confirmed, the split across it is not.
    """
    conf = load_conf("market")["recharge"]["denomination_weights"]
    weights = np.asarray(conf["values"], dtype=float)
    return weights / weights.sum()


def map_to_lyd_ladder(ordinal: pd.Series) -> pd.Series:
    """Quantile-map an ordinal or continuous spend field onto the ladder.

    Each input value's rank becomes a position in the cumulative weight
    distribution, and that position selects a denomination. So the mapping
    honours both the *order* of the real data and the *assumed popularity* of
    each card, which a plain equal-width quantile cut would not.

    Ties are broken by average rank, so a field like `Charge Amount` with only
    ten distinct values spreads across the ladder instead of collapsing onto
    two rungs.
    """
    ladder = np.asarray(recharge_ladder(), dtype=float)
    cumulative = np.cumsum(ladder_weights())

    values = pd.to_numeric(ordinal, errors="coerce")
    if values.notna().sum() == 0:
        raise ValueError("nothing numeric to map")

    # Percentile rank in [0, 1). `pct=True` with average ties gives (0, 1], so
    # nudge off the top edge to keep searchsorted inside the ladder.
    percentile = values.rank(pct=True, method="average").clip(upper=1 - 1e-12)
    index = np.searchsorted(cumulative, percentile.to_numpy(), side="right")
    index = np.clip(index, 0, len(ladder) - 1)

    mapped = pd.Series(ladder[index], index=ordinal.index, dtype="float64")
    mapped[values.isna()] = np.nan

    log.info(
        "quantile_map: %d values -> ladder %s, realised shares %s",
        int(values.notna().sum()),
        tuple(int(v) for v in ladder),
        {int(k): round(v, 3) for k, v in mapped.value_counts(normalize=True).sort_index().items()},
    )
    return mapped


def match_empirical_marginals(real: pd.DataFrame, synthetic: pd.DataFrame) -> pd.DataFrame:
    """Replace each synthetic column's values with the real empirical quantiles
    at the same ranks, keeping the generator's dependence structure.

    THIS IS WHAT A COPULA IS FOR. Sklar's theorem says a joint distribution
    splits into a dependence structure and a set of marginals, and the two can
    be chosen independently. SDV fits both: the Gaussian copula for the
    dependence, and a parametric family per column for the marginals. The
    dependence half works well here -- measured correlation delta 0.047 against
    a 0.10 threshold. The parametric half is the weak link, and badly:

        column                     real max   synthetic max   solo detector AUC
        incoming_outgoing_ratio       24.00            8.30              0.974
        voice_minutes_30d           7667.75         2493.28              0.662
        revenue_source_units         623.50          253.85              0.601

    Every tail is truncated, and a Gamma fit piles 40% of the mass on zero
    where the real data has 3.5%. No choice among the available families fixes
    it -- the two that could, `gaussian_kde` and `truncnorm`, both abort at the
    C level in this build.

    So the marginals are taken from the data instead of from a fitted family.
    Each synthetic value is replaced by the real value at the same quantile,
    which makes every marginal match the empirical distribution *exactly*:
    identical range, identical quantiles, identical point masses at zero. The
    generator's contribution is the part it is actually good at -- which row
    ranks high on which column, jointly.

    This subsumes `preserve_point_masses` and `enforce_orderings` for any
    column it covers: an exact quantile match restores a zero spike for free,
    because the zeros are in the quantiles.

    Documented, not hidden. It is a substitution of empirical marginals for
    fitted ones, it is the standard construction rather than a trick, and an
    evaluator is entitled to know the population was built this way.
    """
    out = synthetic.copy()
    matched: list[str] = []

    for column in real.columns:
        if column not in out.columns or not pd.api.types.is_numeric_dtype(real[column]):
            continue

        reference = real[column].dropna().to_numpy()
        if reference.size == 0:
            continue
        reference = np.sort(reference)

        values = pd.to_numeric(out[column], errors="coerce")
        if values.notna().sum() == 0:
            continue

        # Rank -> position in the sorted real values. `method="first"` so ties
        # spread across neighbouring real values rather than collapsing onto
        # one, which would create a spike the real data does not have.
        ranks = values.rank(method="first", na_option="keep")
        position = ((ranks - 1) / max(values.notna().sum() - 1, 1) * (reference.size - 1)).round()

        mapped = pd.Series(np.nan, index=out.index, dtype="float64")
        valid = position.notna()
        mapped.loc[valid] = reference[position[valid].astype(int).to_numpy()]

        # Preserve the original dtype where it was integral, so a count stays a
        # count and does not become 3.0000000001.
        out[column] = mapped.astype(real[column].dtype) if not mapped.isna().any() else mapped
        matched.append(column)

    log.info("empirical marginals matched on %d columns: %s", len(matched), matched)
    return out


def preserve_point_masses(
    real: pd.DataFrame, synthetic: pd.DataFrame, min_share: float = 0.01
) -> pd.DataFrame:
    """Restore exact-zero spikes that a continuous generator cannot produce.

    THIS IS WHY THE DETECTOR WINS OTHERWISE. A Gaussian copula draws from a
    continuous distribution, so it generates values *near* zero and never
    exactly zero. Real ratio data is full of exact zeros -- a subscriber who
    received no calls has an incoming/outgoing ratio of precisely 0.0000, and
    7.5% of Cell2Cell subscribers dropped no calls at all.

    So the real frame carries 0.0000 and the synthetic frame carries 0.0013,
    and a tree ensemble splits on that one difference and scores a detection
    AUC of 0.997 while every marginal and every correlation looks fine. The
    tell is structural, not distributional, and no choice of marginal family
    fixes it: point masses are not in the family.

    The correction is rank-preserving. For each column with a material zero
    share in the real data, the lowest-ranked synthetic rows are snapped to
    exactly zero until the share matches. Nobody's position in the
    distribution changes; the spike is simply put back where it belongs.

    Documented rather than hidden, because it is a post-hoc correction to
    generator output and an evaluator is entitled to know the population has
    one.
    """
    out = synthetic.copy()
    corrected: dict[str, float] = {}

    for column in real.columns:
        if column not in out.columns or not pd.api.types.is_numeric_dtype(real[column]):
            continue
        share = float((real[column] == 0).mean())
        if share < min_share:
            continue

        values = out[column].astype("float64")
        target = round(share * len(values))
        if target == 0:
            continue

        generated = int((values == 0).sum())

        if generated < target:
            # Too few zeros: snap the smallest values down. This is the case a
            # Beta or Normal marginal produces -- it never lands on zero.
            threshold = values.nsmallest(target).max()
            values = values.mask(values <= threshold, 0.0)
        elif generated > target:
            # TOO MANY zeros, which is the case nobody expects and which is
            # worse. A Gamma marginal with a small fitted shape piles up at the
            # lower bound: measured here, 40% exact zeros for
            # incoming_outgoing_ratio against 3.5% in the real data. A detector
            # separates on that instantly, and adding zeros cannot fix it.
            #
            # The excess is re-drawn from the real column's positive values,
            # which puts those rows back into the distribution they should have
            # been in rather than leaving them piled on the boundary.
            excess = generated - target
            positives = real.loc[real[column] > 0, column].to_numpy()
            if positives.size:
                rng = np.random.default_rng(len(values))
                zero_positions = np.flatnonzero(values.to_numpy() == 0)
                chosen = rng.choice(zero_positions, size=excess, replace=False)
                values.iloc[chosen] = rng.choice(positives, size=excess, replace=True)

        out[column] = values
        corrected[column] = share

    if corrected:
        log.info(
            "point masses restored on %d columns: %s",
            len(corrected),
            {k: f"{v:.1%}" for k, v in corrected.items()},
        )
    return out


def enforce_orderings(synthetic: pd.DataFrame, orderings: dict[str, str]) -> pd.DataFrame:
    """Restore hard inequalities a copula has no way to know about.

    `active_lines <= household_lines` holds for 100.00% of real Cell2Cell rows:
    you cannot have more active lines than lines. A copula models the
    correlation between the two and nothing more, so it happily generates
    households with three lines of which four are active -- and a detector
    finds every one of them immediately.

    Point masses and orderings are the two structural properties this generator
    cannot express. Both are restored here, after sampling, and both are
    documented for the same reason: they are corrections to generator output,
    not properties it learned.

    ``orderings`` maps a column to the column it must not exceed.
    """
    out = synthetic.copy()
    for lesser, greater in orderings.items():
        if lesser not in out.columns or greater not in out.columns:
            continue
        violations = int((out[lesser] > out[greater]).sum())
        if violations:
            out[lesser] = out[[lesser, greater]].min(axis=1)
            log.info(
                "ordering %s <= %s: corrected %d violations (%.2f%%)",
                lesser,
                greater,
                violations,
                100 * violations / len(out),
            )
    return out


def assert_on_ladder(amounts: pd.Series) -> None:
    """Fail if any generated amount is not a card Almadar prints.

    The synthesis equivalent of the margin floor: cheap to check, and it stops
    the population quietly containing denominations that would make every
    downstream revenue figure unreconcilable with a real price sheet.
    """
    ladder = set(recharge_ladder())
    offenders = sorted(set(amounts.dropna().unique()) - {float(v) for v in ladder})
    if offenders:
        raise ValueError(
            f"invented denominations: {offenders}. The ladder is {sorted(ladder)} "
            "(conf/market.yaml#recharge)."
        )
