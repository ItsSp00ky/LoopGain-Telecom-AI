"""Entry point: `python -m cvm.synthesis.run`  (step 2 of 3)

Fits a generator on the real behavioural backbone, samples the population,
applies quantile mapping and business overlays, generates labels from the
hazard function, and runs the quality gate. A gate failure exits non-zero --
the pipeline must not produce a population that a discriminator can spot.

WHAT THE GENERATOR ACTUALLY LEARNS FROM, because this is the part that decides
whether the population means anything.

Cell2Cell is the only source with the scale and the column separation to carry
a joint distribution: 100,000 rows, placed and received voice as separate
columns, peak and off-peak minutes as separate columns. So the generator is fit
on a REDUCED frame derived from it -- the dozen behavioural quantities that map
onto our feature families -- and not on all 80 columns, most of which describe
a US handset market.

The overlays then add what no public dataset has: recharge cadence, zero-balance
hours, emergency credit, the salary week, the weekend rhythm, and the
06:00-11:00 morning bump. Two overlays DEVIATE from the generator's output
rather than replacing it, which is what makes the grounding claim true rather
than decorative.

THE GATE COMPARES THE GENERATOR TO ITS OWN TRAINING DATA, never to the overlaid
population. The overlays are business rules we wrote on purpose; a detector
should be able to spot them, and gating on that would mean rejecting the Libyan
layer for being Libyan.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from cvm.config import load_conf, settings
from cvm.ingest.hashing import assert_no_raw_identifiers, hash_identifier
from cvm.synthesis import ctgan_engine, overlays
from cvm.synthesis.hazard import assert_label_is_learnable, generate_labels
from cvm.synthesis.quality_gate import enforce, run_gate, split_for_gate
from cvm.synthesis.quantile_map import (
    assert_on_ladder,
    enforce_orderings,
    map_to_lyd_ladder,
    match_empirical_marginals,
)

log = logging.getLogger(__name__)

POPULATION_NAME = "population.parquet"

# Hard inequalities the real data obeys and a copula cannot know about.
# `active_lines <= household_lines` holds for 100.00% of real Cell2Cell rows.
ORDERINGS = {"active_lines": "household_lines"}


def build_real_backbone() -> pd.DataFrame:
    """The reduced real frame the generator learns from.

    Every column here is derived from Cell2Cell, and each one maps onto a
    declared feature family. Ratios are computed rather than passed through,
    because the ratio is the transferable quantity: 300 US voice minutes means
    nothing in Tripoli, but "receives 28% of what they place" does.
    """
    from cvm.ingest.cell2cell import derived_ratios, load

    raw = load()
    ratios = derived_ratios(raw)

    backbone = pd.DataFrame(index=raw.index)
    backbone["incoming_outgoing_ratio"] = ratios["incoming_outgoing_ratio"]
    backbone["usage_decay_ratio"] = ratios["usage_decay_ratio"]
    backbone["revenue_decay_ratio"] = ratios["revenue_decay_ratio"]

    # NAMED FOR WHAT IT ACTUALLY MEASURES. The 0.424 median comes from
    # mou_opkv_Mean / (mou_peav_Mean + mou_opkv_Mean) -- off-peak share of
    # VOICE MINUTES, not of data. Using it to ground an off-peak *data* share
    # is a transfer, and the assumption behind it is that time-of-day activity
    # patterns carry across service types even when volumes do not: whoever was
    # active in the off-peak window then is the kind of subscriber who is
    # active in it now. That is plausible and it is an assumption, so the
    # column is called what it is and the overlay derives the data ratio from
    # it rather than pretending they are the same quantity.
    backbone["offpeak_activity_ratio"] = ratios["offpeak_data_ratio"]

    backbone["tenure_months"] = raw["months"].astype("int16")
    backbone["voice_minutes_30d"] = raw["mou_Mean"]

    # DELIBERATELY NOT HERE: sms_count_30d, data_minutes_30d and
    # data_session_failure_rate.
    #
    # Cell2Cell is a ~2001 US dataset and it is VOICE-ERA. Measured on the
    # file: recv_sms_Mean is 99.1% zeros, drop_dat/plcd_dat is 97.4% zeros,
    # and mou_cdat_Mean is 86.6% zeros. Mobile data barely existed.
    #
    # Those columns do not merely fit badly -- they describe a market that is
    # the opposite of the one we are modelling. Libyan prepaid in 2026 is
    # data-first: Almadar's catalogue is 37 bundles of which almost all are
    # data. Grounding data behaviour on a column that is 97% zeros would be
    # worse than not grounding it, because it would carry the authority of
    # "measured" while asserting that nobody uses data.
    #
    # So data and SMS behaviour comes from the overlays instead, and the
    # proposal says which parts of the population are grounded and which are
    # generated. This source grounds VOICE behaviour, the leakage ratio, the
    # off-peak activity split and the decay ratios. That is what it has.
    placed = raw["plcd_vce_Mean"].where(raw["plcd_vce_Mean"] > 0)
    backbone["dropped_call_rate_30d"] = (raw["drop_vce_Mean"] / placed).clip(0, 1)

    # Short calls matter under a 3-minute block tariff: a subscriber whose
    # calls are all under a minute pays the block rate every time.
    backbone["short_call_share"] = (raw["inonemin_Mean"] / placed).clip(0, 1)

    # ZERO-INFLATION: THE FLAG SURVIVES, THE MAGNITUDE DOES NOT.
    #
    # `custcare_Mean` is 55.7% exact zeros -- most subscribers never call
    # support. That spike is a structural giveaway rather than a distributional
    # one: a copula generates values *near* zero but never exactly zero, so
    # real rows carry 0.0000 and synthetic rows carry 0.0013, and a tree
    # ensemble separates them on that alone. The first gate run scored a
    # detection AUC of 0.9996 with good marginals and good correlations for
    # exactly this reason.
    #
    # The textbook fix is to split into "did it happen" and "how much, given it
    # happened", leaving the magnitude null for the 55.7%. That crashes the
    # copula outright -- a hard abort in native code with no traceback -- so it
    # is not available here.
    #
    # Keeping only the binary is the honest resolution. The signal worth having
    # is "has this subscriber ever contacted support", which is a clean
    # Bernoulli the generator reproduces exactly. The magnitude was a US
    # call-centre artefact and nothing downstream needs it grounded: the
    # `credit` and `distress` families come from the overlays regardless.
    backbone["had_care_contact"] = (raw["custcare_Mean"] > 0).astype("int8")

    # Genuinely integer counts. Cast so SDV's metadata detection sees them as
    # integers and rounds on the way out -- a synthetic household with 2.7
    # lines is another structural giveaway.
    backbone["household_lines"] = raw["uniqsubs"].astype("int16")
    backbone["active_lines"] = raw["actvsubs"].astype("int16")

    # The monetary column the quantile map consumes. Kept in source units here;
    # mapped onto the LYD ladder after sampling, so the generator learns the
    # real spread rather than a five-valued staircase.
    backbone["revenue_source_units"] = raw["avgrev"]

    # A generator cannot learn from a column of nulls, and the derived ratios
    # are undefined for the 3-8% of subscribers who placed no calls. Filling
    # with the median keeps the row (its other columns are informative) without
    # inventing a ratio.
    # No nulls may reach the generator. The copula aborts at the C level on a
    # NaN-containing column -- exit 127, no traceback, nothing to debug from --
    # so this fill is load-bearing rather than tidy-minded.
    nulls = backbone.isna().sum()
    backbone = backbone.fillna(backbone.median(numeric_only=True))
    log.info(
        "backbone: %d x %d from Cell2Cell; filled %d nulls (worst column %s at %d)",
        *backbone.shape,
        int(nulls.sum()),
        nulls.idxmax(),
        int(nulls.max()),
    )
    return backbone


def to_libyan_units(synthetic: pd.DataFrame) -> pd.DataFrame:
    """Quantile-map the monetary column onto the LYD ladder and name fields.

    The generator's `revenue_source_units` is US dollars of monthly revenue. It
    carries the right RANK and the wrong units, so it becomes the modal
    recharge by quantile -- see cvm.synthesis.quantile_map for why a linear
    rescale would be worse.
    """
    out = synthetic.copy()
    if not load_conf("data")["synthesis"]["quantile_mapping"]["enabled"]:
        log.warning("quantile mapping is disabled; the population is in source units")
        return out

    out["generator_modal_recharge_lyd"] = map_to_lyd_ladder(out.pop("revenue_source_units"))
    assert_on_ladder(out["generator_modal_recharge_lyd"])
    return out


def attach_identifiers(df: pd.DataFrame) -> pd.DataFrame:
    """Give every generated subscriber a hashed surrogate id.

    Hashed for consistency with the landed sources, so downstream code has one
    id format. These are not hashed MSISDNs -- there is no real identifier here
    to hash. They are a hash of the source name and the row's position, which
    makes them reproducible under the seed and transparently synthetic.
    """
    salt = settings.require_salt()
    out = df.reset_index(drop=True)
    out.insert(
        0,
        "subscriber_id_hashed",
        pd.Series(
            [hash_identifier(f"synthetic:{i}", salt) for i in range(len(out))], dtype="string"
        ),
    )
    out["snapshot_date"] = pd.Timestamp("2026-09-18")
    out["source"] = "synthetic"
    return out


def inject_realism(df: pd.DataFrame) -> pd.DataFrame:
    """Missingness and measurement noise, deliberately.

    The largest risk in the register is generated data that is too clean making
    models look unrealistically good. A population with no missing values and
    no measurement error is not a hard problem, and a model that scores well on
    it has demonstrated nothing about production.

    Label artefacts are exempt: corrupting the label would be corrupting the
    ground truth, not adding realism.
    """
    from cvm.synthesis.hazard import LABEL_ARTIFACT_FIELDS

    conf = load_conf("data")["synthesis"]["realism_injection"]
    rate, noise_sd = conf["missingness_rate"], conf["measurement_noise_sd"]
    rng = np.random.default_rng(settings.random_seed + 99)

    out = df.copy()
    protected = {"subscriber_id_hashed", "snapshot_date", "source", *LABEL_ARTIFACT_FIELDS}
    numeric = [
        c for c in out.columns if c not in protected and pd.api.types.is_numeric_dtype(out[c])
    ]

    # NOISE APPLIES TO CONTINUOUS MEASUREMENTS ONLY, and the distinction is not
    # fussiness. Multiplicative noise on `modal_recharge_amount_lyd` turns a
    # 5 LYD card into 4.556 -- a denomination Almadar does not print, which
    # `assert_on_ladder` rejects and which would make every revenue figure
    # downstream unreconcilable with a real price sheet. The same argument
    # applies to counts: 2.94 emergency advances is not measurement error, it
    # is a nonsense. Missingness is different and applies to everything -- any
    # field can be missing whatever its type.
    ladder_valued = {"modal_recharge_amount_lyd", "generator_modal_recharge_lyd"}
    continuous = [
        c for c in numeric if c not in ladder_valued and not pd.api.types.is_integer_dtype(out[c])
    ]

    for column in numeric:
        if column in continuous:
            out[column] = out[column].astype("float64") * (1 + rng.normal(0, noise_sd, len(out)))
        mask = rng.random(len(out)) < rate
        out.loc[mask, column] = np.nan

    log.info(
        "realism: %.1f%% missingness on %d columns, %.1f%% noise on the %d continuous ones "
        "(label artefacts, ladder values and counts exempt from noise)",
        100 * rate,
        len(numeric),
        100 * noise_sd,
        len(continuous),
    )
    return out


def main() -> None:
    logging.basicConfig(level=settings.log_level, format="%(levelname)-8s %(message)s")
    settings.require_salt()
    settings.ensure_dirs()

    conf = load_conf("data")["synthesis"]
    n = conf["n_subscribers"]

    # 1. The real behavioural backbone, split for an honest gate. The
    #    generator never sees the holdout, so the detector answers "can you
    #    tell this from real data" rather than "can you tell this from the
    #    rows the generator memorised".
    real = build_real_backbone()
    fit_on, holdout = split_for_gate(real)

    # 2. Fit and sample. A MIXTURE of copulas, one per behavioural cluster: a
    #    single copula imposes one dependence structure on a population that
    #    does not have one, and the rows it puts between clusters are what a
    #    detector finds first. Measured, the mixture takes logistic detection
    #    from 0.593 to 0.511 against a 0.468 floor.
    synthetic, _ = ctgan_engine.fit_and_sample(fit_on, kind="mixture_copula", n=n)

    # 3. Empirical marginals, then the orderings the generator cannot know.
    #
    #    A copula separates dependence from marginals; we keep its dependence
    #    and take the marginals from the data. SDV's fitted families truncate
    #    every tail here -- incoming_outgoing_ratio to 8.3 where the real
    #    maximum is 24.0 -- and no available family fixes it. See
    #    quantile_map.match_empirical_marginals. Applied BEFORE the gate,
    #    because it is part of how the population is constructed rather than a
    #    way of dressing up the score, and logged either way.
    synthetic = enforce_orderings(match_empirical_marginals(fit_on, synthetic), ORDERINGS)

    # 4. The gate, against HELD-OUT real rows, before any overlay touches
    #    either side.
    result = run_gate(holdout, synthetic)
    enforce(result)

    # 5. Libyan units, identifiers, overlays, labels.
    population = attach_identifiers(to_libyan_units(synthetic))
    population = overlays.apply_all(population)
    population = generate_labels(population)
    assert_label_is_learnable(population)

    # 6. Realism last, so noise does not disturb the label draw.
    population = inject_realism(population)

    assert_no_raw_identifiers(population)
    # The ladder assertion runs AFTER realism injection, not before. Noise was
    # silently turning 5 LYD cards into 4.556 until this check was moved here.
    assert_on_ladder(population["modal_recharge_amount_lyd"])
    out_path = settings.synthetic_dir / POPULATION_NAME
    population.to_parquet(out_path, index=False)

    print(f"\n{result.summary()}\n")
    print(f"{'POPULATION':<26}{len(population):>12,} x {population.shape[1]}")
    print(f"{'churn rate':<26}{population['silent_churn_30d'].mean():>12.4f}")
    print(f"{'written to':<26}{out_path}")
    print("\nNext: python -m cvm.features.run")


if __name__ == "__main__":
    main()
