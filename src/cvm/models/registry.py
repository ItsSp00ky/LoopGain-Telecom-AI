"""Model loading and the MLflow registry bridge.

Models are loaded once at API startup, never inside a request handler -- a cold
load mid-request is the fastest way to blow the 200 ms p95 budget.

Every model in this component trains on CPU, so artefacts are produced by the
pipeline rather than shipped in from elsewhere. This module does not train
anything -- it loads.
"""

from __future__ import annotations

import logging
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
                loaded[name] = joblib.load(path)
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
