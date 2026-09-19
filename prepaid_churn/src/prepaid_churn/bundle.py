"""The model bundle (ticket T8): everything a scoring run needs, in one versioned folder.

A bundle is built only from a champion that passed its release gate (decision 13).
`manifest.json` is plain JSON and is read before anything is unpickled, so a bundle
built with other library versions stops with a clear message instead of failing on
its first prediction (a lesson from Ali_Branch, where a pickle loaded fine and the
first request failed). Loading then predicts a stored sample row and refuses a bundle
that no longer gives the answer it gave when it was built.
"""

from __future__ import annotations

import hashlib
import json
import pickle
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING

import joblib
import numpy as np
import pandas as pd

from prepaid_churn.schema import contract_markdown

if TYPE_CHECKING:  # the CLI imports BundleError, so model libraries load only when needed
    from prepaid_churn.evaluation import Champion

MANIFEST_FILE = "manifest.json"
MODEL_FILE = "model.joblib"
# Pickled models are only guaranteed to load and predict under the versions that wrote them.
LIBRARIES = ("scikit-learn", "lightgbm", "numpy", "pandas")


class BundleError(RuntimeError):
    """A bundle cannot be built or used; the message says why."""


@dataclass
class Bundle:
    manifest: dict
    champion: Champion
    sample: pd.DataFrame  # one row of model features, predicted again at every load

    @property
    def version(self) -> str:
        return self.manifest["version"]

    @property
    def features(self) -> list[str]:
        return self.manifest["features"]


def contract_version() -> str:
    """Fingerprint of the data contract; a bundle only scores exports of the same contract."""
    return hashlib.sha256(contract_markdown().encode("utf-8")).hexdigest()[:12]


def library_versions() -> dict[str, str]:
    return {name: version(name) for name in LIBRARIES}


def build_bundle(champion: Champion, gate: dict, examples: pd.DataFrame, created_at: str) -> Bundle:
    """Package a gated champion; `examples` are model-ready rows (the first is the sample)."""
    from prepaid_churn.training import feature_columns

    failed = [name for name, check in gate["thresholds"].items() if not check["passed"]]
    if failed or not gate["passed"]:
        raise BundleError(
            f"The champion failed its release gate ({', '.join(failed)}); it cannot be bundled."
        )
    if (gate["champion"], gate["chosen_at"]) != (champion.name, champion.chosen_at):
        raise BundleError("The release gate belongs to another champion; run `churn evaluate`.")
    features = feature_columns(examples)
    sample = examples[features].iloc[[0]].reset_index(drop=True)
    digest = hashlib.sha256(pickle.dumps(champion)).hexdigest()[:8]
    manifest = {
        "version": f"{champion.name}-{champion.chosen_at}-{digest}",
        "created_at": created_at,
        "champion": champion.name,
        "chosen_at": champion.chosen_at,
        "calibration": champion.calibrator.method,
        "risk_thresholds": {
            "high": champion.high_threshold,
            "medium": champion.medium_threshold,
        },
        "features": features,
        "contract_version": contract_version(),
        "libraries": library_versions(),
        "release_gate": gate,
        "validation_metrics": champion.validation,
        "sample_probability": float(champion.predict(sample)[0]),
    }
    return Bundle(manifest, champion, sample)


def save_bundle(bundle: Bundle, directory: str | Path) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / MANIFEST_FILE).write_text(json.dumps(bundle.manifest, indent=2), "utf-8")
    joblib.dump({"champion": bundle.champion, "sample": bundle.sample}, directory / MODEL_FILE)
    return directory


def smoke_check(bundle: Bundle) -> None:
    """Predict the stored sample row; refuse a bundle that cannot, or that answers differently."""
    try:
        probability = float(bundle.champion.predict(bundle.sample)[0])
    except Exception as error:
        raise BundleError(f"The bundle loads but cannot predict: {error}") from error
    expected = bundle.manifest["sample_probability"]
    if not np.isclose(probability, expected, rtol=0, atol=1e-9):
        raise BundleError(
            f"The bundle predicts {probability} for its sample row instead of {expected}."
        )


def load_bundle(directory: str | Path) -> Bundle:
    directory = Path(directory)
    manifest_path = directory / MANIFEST_FILE
    if not manifest_path.exists():
        raise FileNotFoundError(f"{manifest_path} not found. Run `uv run churn bundle` first.")
    manifest = json.loads(manifest_path.read_text("utf-8"))
    problems = [
        f"{name} {built} (installed: {installed})"
        for name, built in manifest["libraries"].items()
        if (installed := version(name)) != built
    ]
    if problems:
        raise BundleError(
            "The bundle was built with other library versions: "
            + ", ".join(problems)
            + ". Run `uv sync` with the lockfile it was built with, or rebuild the bundle."
        )
    if manifest["contract_version"] != contract_version():
        raise BundleError("The bundle was built for another data contract; rebuild it.")
    payload = joblib.load(directory / MODEL_FILE)
    bundle = Bundle(manifest, payload["champion"], payload["sample"])
    smoke_check(bundle)
    return bundle
