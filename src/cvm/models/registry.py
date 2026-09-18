"""Model loading and the MLflow registry bridge.

Models are loaded once at API startup, never inside a request handler -- a cold
load mid-request is the fastest way to blow the 200 ms p95 budget.

The LSTM (M1 Arm B) trains on a free Colab T4 and arrives here as a saved
artefact. This module does not train anything.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_registry(models_dir: Path) -> dict[str, Any]:
    """Load every available model artefact, keyed by the names health.py expects.

    Missing artefacts are logged and skipped rather than raising, so a partial
    deploy reports "degraded" on /health instead of failing to start.
    """
    raise NotImplementedError("TODO(E4)")


def log_run(module: str, params: dict, metrics: dict, artifacts: dict | None = None) -> str:
    """Log one experiment to MLflow. Returns the run id.

    Every module calls this. Definition of Done item 4 is not optional.
    """
    raise NotImplementedError("TODO(E4)")