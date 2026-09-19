"""Model loading and the MLflow registry bridge.

Models are loaded once at API startup, never inside a request handler -- a cold
load mid-request is the fastest way to blow the 200 ms p95 budget.

Every model in this component trains on CPU, so artefacts are produced by the
pipeline rather than shipped in from elsewhere. This module does not train
anything -- it loads.
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# What each health-check name is stored as. The keys are the names
# api/routers/health.py reports, so a rename there fails loudly here rather
# than silently reporting a model as missing forever.
ARTEFACTS: dict[str, tuple[str, str]] = {
    "m1_churn_lightgbm": ("m1_churn.joblib", "joblib"),
    "m1b_survival": ("m1b_cox.joblib", "joblib"),
    "m2_clv": ("m2_bg_nbd.pkl", "lifetimes_bgnbd"),
    "m2_gamma_gamma": ("m2_gamma_gamma.pkl", "lifetimes_gg"),
    "m2_segments": ("m2_kmeans.joblib", "joblib"),
    "m3_uplift": ("m3_uplift.joblib", "joblib"),
    "m4_repayment_pd": ("m4_advance.joblib", "joblib"),
}


def load_registry(models_dir: Path) -> dict[str, Any]:
    """Load every available model artefact, keyed by the names health.py expects.

    Missing artefacts are logged and skipped rather than raising, so a partial
    deploy reports "degraded" on /health instead of failing to start.

    THAT CHOICE CUTS BOTH WAYS and is worth being explicit about. An API that
    refuses to boot without M4 cannot serve churn scores during an M4 outage,
    which is worse. An API that boots silently missing M4 and returns 503 on
    one endpoint is recoverable and visible. What makes the second safe is that
    /health enumerates each model individually -- a single "degraded" with no
    detail would be the worst of both.
    """
    import joblib

    models_dir = Path(models_dir)
    loaded: dict[str, Any] = {}
    missing: list[str] = []

    for name, (filename, kind) in ARTEFACTS.items():
        path = models_dir / filename
        if not path.exists():
            missing.append(name)
            continue
        try:
            if kind == "joblib":
                # sklearn emits InconsistentVersionWarning when a pickle was
                # written by a different version, and says plainly that this
                # "might lead to breaking code OR INVALID RESULTS". It is a
                # warning, so it goes to stderr and nobody reads it: the
                # serving image ran sklearn 1.9.1 against 1.7.2 artefacts and
                # printed four of these before returning 500 on the first
                # request. Promoted to an error log, because the silent case --
                # a skewed pickle that still predicts, just wrongly -- is the
                # one no smoke check can catch.
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    loaded[name] = joblib.load(path)
                for w in caught:
                    if type(w.message).__name__ == "InconsistentVersionWarning":
                        log.error("VERSION SKEW loading %s: %s", name, w.message)
            elif kind == "lifetimes_bgnbd":
                from lifetimes import BetaGeoFitter

                model = BetaGeoFitter()
                model.load_model(str(path))
                loaded[name] = model
            elif kind == "lifetimes_gg":
                from lifetimes import GammaGammaFitter

                model = GammaGammaFitter()
                model.load_model(str(path))
                loaded[name] = model
        except Exception as exc:  # a corrupt artefact must not stop startup
            log.error("could not load %s from %s: %s", name, path, exc)
            missing.append(name)

    log.info(
        "registry: %d of %d artefacts loaded from %s%s",
        len(loaded),
        len(ARTEFACTS),
        models_dir,
        f"; MISSING {missing}" if missing else "",
    )
    return loaded


def log_run(module: str, params: dict, metrics: dict, artifacts: dict | None = None) -> str:
    """Log one experiment to MLflow. Returns the run id.

    Every module calls this. Definition of Done item 4 is not optional.

    DEGRADES TO A LOCAL FILE WHEN NO TRACKING SERVER IS UP, rather than raising
    or silently doing nothing. A training run that fails at the end because
    MLflow is unreachable has thrown away the training; a run that logs nothing
    and says nothing has thrown away the record. Writing JSON beside the
    reports keeps the Definition of Done satisfiable on a laptop with no server.
    """
    import json
    import uuid
    from datetime import UTC, datetime

    from cvm.config import settings

    run_id = str(uuid.uuid4())
    record = {
        "run_id": run_id,
        "module": module,
        "logged_at": datetime.now(UTC).isoformat(),
        "params": params,
        "metrics": metrics,
        "artifacts": artifacts or {},
    }

    try:
        import mlflow

        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        mlflow.set_experiment(settings.mlflow_experiment)
        with mlflow.start_run(run_name=module) as run:
            mlflow.log_params(params)
            mlflow.log_metrics({k: v for k, v in metrics.items() if isinstance(v, int | float)})
            run_id = run.info.run_id
        log.info("mlflow: logged %s as run %s", module, run_id)
        return run_id
    except Exception as exc:  # the fallback IS the handling; see the docstring
        fallback = settings.reports_dir / "mlflow_offline"
        fallback.mkdir(parents=True, exist_ok=True)
        (fallback / f"{module}_{run_id}.json").write_text(json.dumps(record, indent=2, default=str))
        log.warning("mlflow unreachable (%s); logged %s offline to %s", exc, module, fallback)
        return run_id


def _feature_names(estimator: Any, bundle: Any) -> list[str] | None:
    """Where a fitted estimator records the columns it was trained on.

    Four places, because four libraries. None means "cannot be smoke-checked"
    and is reported as a skip rather than a pass -- a check that silently
    succeeds when it could not run is worse than no check.
    """
    if isinstance(bundle, dict) and isinstance(bundle.get("columns"), list):
        return list(bundle["columns"])
    for attr in ("columns", "feature_names_in_", "feature_name_"):
        names = getattr(estimator, attr, None)
        if names is not None and len(names) > 0:
            return [str(c) for c in names]
    return None


def smoke_check(models: dict[str, Any]) -> dict[str, str]:
    """Push one row through every loaded scorer. Returns name -> error message.

    LOADING IS NOT WORKING, and the gap between them is not theoretical. The
    serving image resolved scikit-learn 1.9.1 against artefacts pickled by
    1.7.2. Every artefact deserialised without complaint, load_registry logged
    "7 of 7 artefacts loaded", /health reported "ok", the container was marked
    healthy -- and the first real request returned 500 with
    `'SimpleImputer' object has no attribute '_fill_dtype'`, a private
    attribute the newer transform() reads and the older fit() never wrote.

    A readiness check that only proves deserialisation cannot see that. This
    runs one zero-filled row through each estimator's predict_proba, which
    exercises the whole pipeline -- imputer, scaler, booster -- at startup,
    where a failure costs a restart instead of a demo.

    Zeros are a legitimate input here and not a shortcut: every column in the
    matrix is a count, a ratio or a currency amount, so an all-zero row is a
    subscriber with no activity. The check asserts the call SUCCEEDS, never
    that the probability means anything.
    """
    import numpy as np
    import pandas as pd

    failures: dict[str, str] = {}
    checked = 0

    for name, bundle in models.items():
        estimators: list[tuple[str, Any]] = []
        if isinstance(bundle, dict):
            inner = bundle.get("model")
            if inner is not None:
                estimators.append((name, inner))
            else:  # m3_uplift is {treated, control}; m4 is {airtime, data}
                estimators.extend(
                    (f"{name}.{k}", v) for k, v in bundle.items() if hasattr(v, "predict_proba")
                )
        elif hasattr(bundle, "predict_proba"):
            estimators.append((name, bundle))

        for label, estimator in estimators:
            columns = _feature_names(estimator, bundle)
            if columns is None:
                log.warning("smoke check: %s exposes no feature names; SKIPPED, not passed", label)
                continue
            try:
                row = pd.DataFrame(np.zeros((1, len(columns))), columns=columns)
                estimator.predict_proba(row)
                checked += 1
            except Exception as exc:
                failures[label] = f"{type(exc).__name__}: {exc}"
                log.error("smoke check: %s loaded but CANNOT PREDICT -- %s", label, exc)

    log.info(
        "smoke check: %d estimator(s) predicted a row%s",
        checked,
        f"; {len(failures)} FAILED {sorted(failures)}" if failures else "",
    )
    return failures
