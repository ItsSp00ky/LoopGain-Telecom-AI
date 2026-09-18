"""Dataset F -- Criteo Uplift.  VALIDATION SOURCE.  Owner: E1

25 million rows from a real randomised incrementality test: genuine treatment
and control arms, assigned at random, with the outcome observed for both.

THIS IS THE ANSWER TO THE HARDEST QUESTION THE PROJECT FACES. Our subscriber
population is generated, so "your uplift model scores well on data you made up"
is a fair challenge. It is answered by training and evaluating the M3 *method*
here first -- on data nobody generated -- and only then applying the validated
method to the Libyan population. What remains synthetic is the population, and
we say so.

Without this, every Qini number in the report is a statement about our own
hazard function rather than about uplift modelling. That is the difference
between a measurement and an assertion, which is why the roadmap fetches this
in phase 1 rather than when M3 is ready.

NOT FETCHED THROUGH scikit-uplift. `sklift.datasets.fetch_criteo` points at a
hardcoded S3 bucket that now returns 403, and Criteo's own go.criteo.net link
returns 404. Both are dead. The dataset is still published on HuggingFace, so
this module downloads from there directly -- no credential, no `datasets`
dependency, one 311 MB file, cached on first use.

That is worth knowing before phase 6: the library everyone reaches for cannot
fetch the data this project's strongest claim depends on, and the failure is a
403 several layers down rather than an obvious message.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from cvm.config import load_conf, settings

log = logging.getLogger(__name__)

TREATMENT = "treatment"
# `visit` rather than `conversion`: it is the denser signal (~4.9% vs ~0.3%),
# and a 0.3% base rate needs far more rows to estimate an uplift from. The
# method is what we are validating, not Criteo's conversion funnel.
OUTCOME = "visit"

# NEITHER OF THESE MAY BE A FEATURE, and both are in the file next to the ones
# that may.
#
# `conversion` is strictly downstream of `visit` -- a user who converted
#   visited -- so it is the label in a thin disguise. A model given it scores
#   beautifully and has learned nothing.
# `exposure` is whether a treated user was actually shown the ad. It is decided
#   AFTER assignment, so conditioning on it breaks the randomisation that makes
#   this dataset worth using at all. Post-treatment variables are the classic
#   way an uplift study quietly stops being an uplift study.
#
# This is the same driver/artefact distinction the synthesis layer makes, met
# here in real data rather than generated data.
POST_TREATMENT_COLUMNS = ("conversion", "exposure")


def _conf() -> dict:
    return load_conf("data")["sources"]["criteo_uplift"]


SOURCE_URL = (
    "https://huggingface.co/datasets/criteo/criteo-uplift/resolve/main/"
    "criteo-research-uplift-v2.1.csv.gz"
)
ARCHIVE_NAME = "criteo-research-uplift-v2.1.csv.gz"
SAMPLE_NAME = "criteo_uplift_10pct.parquet"


def _download_archive() -> Path:
    """Fetch the 311 MB gzip once and keep it. Returns the local path."""
    archive = settings.external_dir / ARCHIVE_NAME
    if archive.exists():
        log.info("criteo: using archive %s (%.0f MB)", archive, archive.stat().st_size / 1e6)
        return archive

    import shutil
    import urllib.request

    settings.external_dir.mkdir(parents=True, exist_ok=True)
    log.info("criteo: downloading %s (311 MB, once)", SOURCE_URL)
    request = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"})
    # Streamed to a .part file so an interrupted download cannot leave a
    # truncated archive that looks cached. A 311 MB re-download is expensive
    # enough that this is worth four lines.
    partial = archive.with_suffix(archive.suffix + ".part")
    with urllib.request.urlopen(request, timeout=600) as response, partial.open("wb") as out:
        shutil.copyfileobj(response, out, length=1 << 20)
    partial.replace(archive)
    log.info("criteo: cached %.0f MB to %s", archive.stat().st_size / 1e6, archive)
    return archive


def fetch(sample_10pct: bool = True) -> pd.DataFrame:
    """Read the Criteo table, cached under data/external/.

    ``sample_10pct`` defaults to True: 1.4M rows is ample to estimate a Qini
    curve and loads in seconds instead of minutes. Pass False for the full set
    when reporting the headline number.

    The sample is written to its own Parquet file, seeded from
    ``settings.random_seed``, so the warm-up set is identical between runs --
    an uplift number that moves because the sample moved is not a result.
    """
    sample_cache = settings.external_dir / SAMPLE_NAME
    if sample_10pct and sample_cache.exists():
        log.info("criteo: using 10%% sample cache %s", sample_cache)
        return pd.read_parquet(sample_cache)

    archive = _download_archive()

    if not sample_10pct:
        # ~14M rows x 14 columns. Peak memory is several GB; this path exists
        # for the headline number, not for iterating.
        log.info("criteo: reading the FULL table from %s -- this needs real memory", archive)
        df = pd.read_csv(archive, compression="gzip")
        log.info("criteo: %d rows, %d columns", len(df), df.shape[1])
        return df

    # SAMPLED DURING THE READ, not after it. Reading 14M rows in order to throw
    # 90% away spikes memory for no reason, on a machine with ~20 GB free and a
    # 3 GB serving budget. Chunked sampling keeps the peak at one chunk.
    log.info("criteo: streaming %s and sampling 10%% as it goes", archive)
    chunks: list[pd.DataFrame] = []
    rows_seen = 0
    for i, chunk in enumerate(pd.read_csv(archive, compression="gzip", chunksize=1_000_000)):
        rows_seen += len(chunk)
        # Seed per chunk so the sample is reproducible AND independent of how
        # pandas happens to size the final partial chunk.
        chunks.append(chunk.sample(frac=0.10, random_state=settings.random_seed + i))
        if i % 5 == 0:
            log.info("criteo: %d rows read, %d sampled", rows_seen, sum(len(c) for c in chunks))

    df = pd.concat(chunks, ignore_index=True)
    log.info("criteo: %d rows read, %d sampled (%d columns)", rows_seen, len(df), df.shape[1])

    df.to_parquet(sample_cache, index=False)
    log.info("criteo: cached the sample to %s", sample_cache)
    return df


def load(sample_10pct: bool = True) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Return (X, y, treatment) ready for a two-model uplift fit.

    No hashing: there is no identifier in this source. Criteo's features are
    anonymised floats with no documented meaning, which is fine -- we are
    validating a *method*, not interpreting coefficients.
    """
    df = fetch(sample_10pct=sample_10pct)
    y = df[OUTCOME].astype(int)
    t = df[TREATMENT].astype(int)

    dropped = [c for c in (OUTCOME, TREATMENT, *POST_TREATMENT_COLUMNS) if c in df.columns]
    x = df.drop(columns=dropped)

    leaked = [c for c in POST_TREATMENT_COLUMNS if c in x.columns]
    if leaked:
        raise AssertionError(f"post-treatment columns reached the feature matrix: {leaked}")
    log.info("criteo: %d features, dropped %s", x.shape[1], dropped)

    assert_randomised(t, y)
    return x, y, t


def assert_randomised(treatment: pd.Series, outcome: pd.Series) -> dict[str, float]:
    """Confirm the arms look randomised, and report the naive lift.

    Criteo's treatment share is about 85%, which is lopsided but still random
    assignment. What must hold is that BOTH arms are populated -- a single-arm
    dataset cannot identify a treatment effect at all, and would silently turn
    the two-model difference into noise.
    """
    share = float(treatment.mean())
    if not 0.01 < share < 0.99:
        raise ValueError(
            f"treatment share is {share:.4f}: one arm is effectively empty, so no "
            "treatment effect is identifiable from this data."
        )

    treated_rate = float(outcome[treatment == 1].mean())
    control_rate = float(outcome[treatment == 0].mean())
    stats = {
        "treatment_share": share,
        "outcome_rate_treated": treated_rate,
        "outcome_rate_control": control_rate,
        "naive_lift_pp": (treated_rate - control_rate) * 100,
    }
    log.info(
        "criteo: treated %.1f%% | outcome %.4f treated vs %.4f control | naive lift %.3f pp",
        share * 100,
        treated_rate,
        control_rate,
        stats["naive_lift_pp"],
    )
    return stats
