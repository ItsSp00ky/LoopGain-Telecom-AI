"""Segment discovery.  Owner: E3

    K-Means on scaled RFM-LE, k chosen by silhouette + elbow
    Hierarchical clustering with a dendrogram -- structural cross-check: are
        the eight business segments natural, or imposed?
    PCA for 2-D visualisation, and to check how much RFM-LE variance actually
        sits in two components

Hierarchical clustering is the first thing to cut if the week gets tight;
K-Means and PCA carry the screen on their own.

WHY THREE TECHNIQUES AND NOT ONE. They answer different questions. K-Means
asks how the base actually clusters; PCA asks how many dimensions RFM-LE really
has; hierarchical asks whether the eight business segments are a natural shape
in the data or a grid we imposed on it. The last one is the uncomfortable
question and it is the reason the module exists -- if the dendrogram cuts
nowhere near eight, the segments are a reporting convention rather than a
finding, and the dashboard should say so.

Where the rules and the clusters disagree, the disagreement is the insight.
Perfect agreement would mean one of them is redundant.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from cvm.config import load_conf, settings

log = logging.getLogger(__name__)

# The five dimensions, scaled. Deliberately the QUINTILES rather than the raw
# values: the raw ones are on wildly different scales with heavy tails, and
# K-Means on a Euclidean metric would cluster almost entirely on whichever
# happened to have the largest variance.
DIMENSIONS = ("R", "F", "M", "L", "E")

# Ward linkage is O(n^2) in memory. At 100,000 subscribers the distance matrix
# alone is 40 GB, so the structural cross-check runs on a sample and says so.
HIERARCHICAL_SAMPLE = 5_000


def _conf() -> dict:
    return load_conf("models/m2_value")["segmentation"]


def design(df: pd.DataFrame) -> pd.DataFrame:
    """The scaled RFM-LE matrix every technique here consumes."""
    from sklearn.preprocessing import StandardScaler

    missing = [d for d in DIMENSIONS if d not in df.columns]
    if missing:
        raise KeyError(f"{missing} absent; RFM-LE quintiles come from cvm.features.rfm_le")

    raw = df[list(DIMENSIONS)].astype("float64")
    scaled = StandardScaler().fit_transform(raw)
    return pd.DataFrame(scaled, columns=list(DIMENSIONS), index=df.index)


def fit_kmeans(rfm: pd.DataFrame, k_search: tuple[int, ...] | None = None):
    """Fit across k, select by silhouette and elbow, return the chosen model.

    SILHOUETTE DECIDES, and the elbow is reported beside it. The elbow is read
    off a chart by eye, which means two people get two answers and neither can
    defend theirs; silhouette is a number, so the choice is reproducible and
    arguable. Where they disagree the disagreement is logged -- it usually
    means the structure is weak, which is itself worth knowing before anyone
    builds a campaign on the clusters.

    Silhouette is computed on a SAMPLE. It is O(n^2) in the number of points
    and 100,000 subscribers is 10^10 pairwise distances per k.
    """
    from sklearn.cluster import KMeans
    from sklearn.metrics import calinski_harabasz_score, davies_bouldin_score, silhouette_score

    conf = _conf()["kmeans"]
    k_search = tuple(conf["k_search"]) if k_search is None else k_search
    X = design(rfm)

    sample = X.sample(min(10_000, len(X)), random_state=settings.random_seed)

    rows = []
    models = {}
    for k in k_search:
        model = KMeans(n_clusters=k, n_init=conf["n_init"], random_state=settings.random_seed)
        model.fit(X)
        models[k] = model
        rows.append(
            {
                "k": k,
                "inertia": float(model.inertia_),
                "silhouette": float(silhouette_score(sample, model.predict(sample))),
                "davies_bouldin": float(davies_bouldin_score(sample, model.predict(sample))),
                "calinski_harabasz": float(calinski_harabasz_score(sample, model.predict(sample))),
            }
        )

    scores = pd.DataFrame(rows)
    by_silhouette = int(scores.loc[scores["silhouette"].idxmax(), "k"])
    by_elbow = _elbow(scores)

    if by_silhouette != by_elbow:
        log.info(
            "k: silhouette says %d, the elbow says %d. Silhouette decides, because an "
            "elbow is read by eye and cannot be defended; the disagreement usually means "
            "the structure is weak.",
            by_silhouette,
            by_elbow,
        )

    chosen = models[by_silhouette]
    best = scores.loc[scores["k"] == by_silhouette].iloc[0]
    log.info(
        "kmeans: k=%d by silhouette %.4f (davies-bouldin %.3f, calinski-harabasz %.0f) "
        "over k in %s",
        by_silhouette,
        best["silhouette"],
        best["davies_bouldin"],
        best["calinski_harabasz"],
        list(k_search),
    )
    return chosen, scores, by_elbow


def _elbow(scores: pd.DataFrame) -> int:
    """The k of maximum curvature in the inertia curve.

    Computed rather than eyeballed, by the standard trick: the point furthest
    from the straight line joining the first and last. It is still a heuristic
    -- that is why silhouette decides -- but at least it is the SAME heuristic
    every time it runs.
    """
    k = scores["k"].to_numpy(dtype="float64")
    inertia = scores["inertia"].to_numpy(dtype="float64")
    if len(k) < 3:
        return int(k[0])

    start, end = np.array([k[0], inertia[0]]), np.array([k[-1], inertia[-1]])
    line = end - start
    line = line / np.linalg.norm(line)

    distances = []
    for i in range(len(k)):
        point = np.array([k[i], inertia[i]]) - start
        distances.append(np.linalg.norm(point - np.dot(point, line) * line))
    return int(k[int(np.argmax(distances))])


def fit_hierarchical(rfm: pd.DataFrame, sample_size: int | None = None):
    """Ward linkage on a sample. The structural cross-check.

    THE QUESTION THIS ANSWERS is not "what are the clusters" -- K-Means already
    said. It is whether EIGHT is a natural number of groups in this data or a
    figure we chose because eight business segments read well on a slide. If
    the dendrogram's own best cut is nowhere near eight, the segments are a
    reporting convention, and the report should say so rather than imply the
    data produced them.

    On a sample because Ward is O(n^2) in memory: the full distance matrix at
    100,000 subscribers is about 40 GB.
    """
    from scipy.cluster.hierarchy import linkage

    conf = _conf()["hierarchical"]
    sample_size = HIERARCHICAL_SAMPLE if sample_size is None else sample_size

    X = design(rfm)
    if len(X) > sample_size:
        X = X.sample(sample_size, random_state=settings.random_seed)
        log.info(
            "hierarchical: sampled %d of %d rows -- Ward is O(n^2) in memory", sample_size, len(rfm)
        )

    matrix = linkage(X.to_numpy(), method=conf["linkage"], metric=conf["metric"])
    log.info("hierarchical: %s linkage over %d rows", conf["linkage"], len(X))
    return matrix, X


def dendrogram_data(model, max_clusters: int = 12) -> pd.DataFrame:
    """Merge heights and the implied cut, for the plot and for the verdict.

    Returns one row per candidate cut: how many clusters it gives, the distance
    at which they merge, and the GAP to the next merge. The largest gap is the
    dendrogram's own opinion about how many groups there are -- the cut you
    would make by eye, computed so it does not depend on the eye.
    """
    from scipy.cluster.hierarchy import fcluster

    heights = np.sort(model[:, 2])[::-1][: max_clusters + 1]
    rows = []
    for i in range(1, min(max_clusters, len(heights))):
        rows.append(
            {
                "clusters": i + 1,
                "merge_height": float(heights[i - 1]),
                "gap_to_next": float(heights[i - 1] - heights[i]),
            }
        )

    frame = pd.DataFrame(rows)
    natural = int(frame.loc[frame["gap_to_next"].idxmax(), "clusters"])
    frame.attrs["natural_clusters"] = natural
    frame.attrs["labels_at_natural"] = fcluster(model, t=natural, criterion="maxclust")

    log.info(
        "dendrogram: the largest merge gap is at %d clusters%s",
        natural,
        (
            " -- the eight business segments are NOT the natural shape of this data, so "
            "they are a reporting convention and the dashboard should say so"
            if natural != 8
            else " -- which matches the eight business segments"
        ),
    )
    return frame


def fit_pca(rfm: pd.DataFrame, n_components: int | None = None):
    """Also report explained variance -- the interesting number, not the plot.

    If two components carry most of the variance, RFM-LE has fewer real
    dimensions than its five names suggest, and some of them are measuring the
    same thing under different labels. That is a finding about the feature
    design, not a plotting convenience.
    """
    from sklearn.decomposition import PCA

    conf = _conf()["pca"]
    n_components = conf["n_components"] if n_components is None else n_components

    X = design(rfm)
    model = PCA(n_components=n_components, random_state=settings.random_seed)
    projected = model.fit_transform(X)

    explained = model.explained_variance_ratio_
    loadings = pd.DataFrame(
        model.components_.T,
        index=list(DIMENSIONS),
        columns=[f"PC{i + 1}" for i in range(n_components)],
    )

    log.info(
        "pca: %d components carry %.1f%% of RFM-LE variance (%s)%s",
        n_components,
        100 * explained.sum(),
        ", ".join(f"PC{i + 1} {v:.1%}" for i, v in enumerate(explained)),
        (
            " -- most of the five dimensions are measuring the same thing"
            if explained.sum() > 0.8
            else " -- the five dimensions are carrying genuinely different information"
        ),
    )
    return model, pd.DataFrame(projected, index=X.index, columns=loadings.columns), loadings


def compare_rules_vs_clusters(rule_segments: pd.Series, cluster_labels: pd.Series) -> pd.DataFrame:
    """Cross-tab. The cells that disagree are the dashboard insight.

    "Disagreement" needs a definition, because the two labellings have no
    shared vocabulary -- cluster 3 is not trying to be `At-Risk Valuable`. So
    each cluster is MAPPED to the rule segment it most overlaps, and a
    subscriber disagrees when their rule segment is not their cluster's
    plurality segment. That is the honest reading: the clusters put them with a
    crowd the rules would have sent elsewhere.

    Adjusted Rand and mutual information are reported beside it, because those
    are label-invariant and do not depend on the mapping at all.

    MIND THE GRANULARITY when reading the agreement. Adjusted Rand between 3
    clusters and 8 rule segments is bounded well below 1 no matter how good
    either labelling is -- three groups cannot reproduce eight. A low score at
    mismatched k is arithmetic, not a finding. `run.py` therefore reports this
    at BOTH the silhouette-chosen k and at k = 8, and only the second one is
    evidence about whether the rules describe real structure.
    """
    from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

    rules = pd.Series(rule_segments).astype(str).reset_index(drop=True)
    clusters = pd.Series(cluster_labels).astype(int).reset_index(drop=True)
    if len(rules) != len(clusters):
        raise ValueError(f"{len(rules)} rule labels against {len(clusters)} cluster labels")

    crosstab = pd.crosstab(clusters, rules)
    plurality = crosstab.idxmax(axis=1)

    mapped = clusters.map(plurality)
    disagrees = mapped != rules

    crosstab.attrs["disagreement_share"] = float(disagrees.mean())
    crosstab.attrs["adjusted_rand"] = float(adjusted_rand_score(rules, clusters))
    crosstab.attrs["normalised_mutual_info"] = float(normalized_mutual_info_score(rules, clusters))
    crosstab.attrs["plurality_map"] = plurality.to_dict()

    # A cluster that no segment dominates is one the rules have no word for,
    # which is the most interesting thing this function can find.
    purity = (crosstab.max(axis=1) / crosstab.sum(axis=1)).round(3)
    crosstab.attrs["cluster_purity"] = purity.to_dict()

    log.info(
        "rules vs clusters: %.1f%% disagree, adjusted Rand %.3f, NMI %.3f; "
        "least-pure cluster %s at %.1f%% -- the rules have no single word for it",
        100 * crosstab.attrs["disagreement_share"],
        crosstab.attrs["adjusted_rand"],
        crosstab.attrs["normalised_mutual_info"],
        purity.idxmin(),
        100 * purity.min(),
    )
    return crosstab
