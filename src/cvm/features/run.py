"""Entry point: `python -m cvm.features.run`  (step 3 of 3)

Builds the RFM-LE quintiles, the decay, distress, leakage and network-quality
families, and both feature stores.

THE ORDER HERE IS THE POINT, and it is the one thing in this file worth
reading twice:

    1. load the population          (labels attached, artefacts present)
    2. build every feature family   (from the population, before any split)
    3. SPLIT TEMPORALLY             (while snapshot_date still exists)
    4. DROP THE EXCLUDED COLUMNS    (artefacts and snapshot_date, after)
    5. write both stores

Steps 3 and 4 are in that order deliberately. `snapshot_date` is on the
excluded list because it would leak the split, and it is also the column the
split is made on -- so dropping first would make a temporal split impossible
and dropping never would leak. Doing it in this order is not an accident, and
it is why `drop_excluded_columns` takes a `keep_snapshot` flag.
"""

from __future__ import annotations

import logging

import pandas as pd

from cvm.config import load_conf, settings
from cvm.features import distress, rfm_le, splits, store, velocity, wallet_leakage

log = logging.getLogger(__name__)

NETWORK_QUALITY_FIELDS = (
    "dropped_call_rate_30d",
    "data_session_failure_rate",
    "service_outage_hours_30d",
)


def load_population() -> pd.DataFrame:
    """The labelled population from Layer 2."""
    path = settings.synthetic_dir / "population.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} does not exist. Layer 3 reads what Layer 2 writes; run "
            "`python -m cvm.synthesis.run` first (phase 2)."
        )
    population = pd.read_parquet(path)
    log.info("population: %d x %d from %s", *population.shape, path)
    return population


def build_features(population: pd.DataFrame) -> pd.DataFrame:
    """Every feature family, joined on the population index.

    Families are built independently and joined, rather than mutating one
    frame in sequence, so a bug in one cannot silently corrupt another and so
    each can be tested on its own.
    """
    identity = population[["subscriber_id_hashed", "snapshot_date"]].copy()

    families = {
        "velocity": velocity.build(population),
        "distress": distress.build(population),
        "leakage": wallet_leakage.build(population),
        "rfm_le": rfm_le.build(population),
    }

    # Network quality passes through unchanged. It is subscriber-level and
    # already measured; Component 2 will supply better values for the same
    # field names when it lands, and nothing in M1 changes when it does.
    network = population[[c for c in NETWORK_QUALITY_FIELDS if c in population.columns]]
    families["network_quality"] = network

    # The calendar family, and the label artefacts. The artefacts ride along
    # to this point so the split can carry the label, and are dropped by name
    # afterwards -- never silently.
    carried = [
        c
        for c in (
            "is_salary_week",
            "weekend_usage_share_30d",
            "is_weekend_heavy",
            "morning_pass_propensity",
            "offpeak_data_ratio",
            "tenure_months",
            "silent_churn_30d",
            "hazard_score",
            "days_to_churn",
            "churn_date",
        )
        if c in population.columns
    ]
    families["carried"] = population[carried]

    features = identity
    for name, frame in families.items():
        overlapping = set(features.columns) & set(frame.columns)
        if overlapping:
            frame = frame.drop(columns=list(overlapping))
        features = features.join(frame)
        log.info("  + %-16s %3d columns", name, frame.shape[1])

    log.info("features: %d x %d", *features.shape)
    return features


def main() -> None:
    logging.basicConfig(level=settings.log_level, format="%(levelname)-8s %(message)s")
    settings.ensure_dirs()

    population = load_population()
    features = build_features(population)

    # 3. SPLIT FIRST, while snapshot_date still exists.
    train, validation, test = splits.temporal_split(features)

    # The framing assertion, on real dates rather than on trust. The feature
    # window ends at a subscriber's snapshot; the label window opens gap_days
    # later. If that ever stops holding, every metric downstream is invalid.
    windows = load_conf("features")["windows"]
    latest_feature_date = pd.to_datetime(features["snapshot_date"]).max()
    splits.assert_no_window_overlap(
        latest_feature_date,
        latest_feature_date + pd.Timedelta(days=windows["gap_days"]),
    )

    # 4. DROP SECOND. The artefacts go; the partition key and the LABEL stay,
    #    because this is the training matrix and a store with no target is a
    #    store nothing can be trained on.
    offline = splits.drop_excluded_columns(features, keep_snapshot=True, keep_target=True)
    n_dropped = features.shape[1] - offline.shape[1]

    # 5. Both stores. Offline keeps every snapshot for training; online keeps
    #    the latest per subscriber for serving.
    store.write_offline(offline)
    store.build_online(offline)

    print(f"\n{'SPLIT':<14}{'ROWS':>10}{'SHARE':>9}  SNAPSHOT RANGE")
    print("-" * 62)
    for name, part in (("train", train), ("validation", validation), ("test", test)):
        dates = pd.to_datetime(part["snapshot_date"])
        print(
            f"{name:<14}{len(part):>10,}{len(part) / len(features):>8.1%}  "
            f"{dates.min().date()} to {dates.max().date()}"
        )
    print("-" * 62)
    print(f"{'features':<14}{offline.shape[1]:>10} columns ({n_dropped} excluded and dropped)")
    print(f"{'offline':<14}{settings.feature_store_offline!s}")
    print(f"{'online':<14}{settings.feature_store!s}")
    print("\nNext: M1 -- see docs/ROADMAP.md#phase-4")


if __name__ == "__main__":
    main()
