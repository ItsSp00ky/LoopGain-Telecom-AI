"""Configuration loading.

Two sources, deliberately separated:

* **Environment** (``.env``) holds secrets, hosts and paths -- anything that
  differs between a laptop, CI and the demo host.
* **YAML** (``conf/``) holds every threshold, weight and boundary. An evaluator
  will ask us to change a guardrail live; that must not require a code edit.

Usage
-----
    from cvm.config import settings, load_conf

    salt = settings.hash_salt
    pricing = load_conf("pricing")
    min_margin = pricing["guardrails"]["margin_floor"]["min_margin"]
"""

from __future__ import annotations

import functools
import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root: src/cvm/config.py -> src/cvm -> src -> root
REPO_ROOT = Path(__file__).resolve().parents[2]
CONF_DIR = REPO_ROOT / "conf"

_ENV_INTERP = re.compile(r"\$\{oc\.env:([A-Z0-9_]+)(?:,([^}]*))?\}")


class Settings(BaseSettings):
    """Environment-backed settings. Everything here can differ per machine."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Runtime ---------------------------------------------------------
    env: str = Field(default="dev", alias="CVM_ENV")
    log_level: str = Field(default="INFO", alias="CVM_LOG_LEVEL")
    random_seed: int = Field(default=606, alias="CVM_RANDOM_SEED")

    # --- Paths -----------------------------------------------------------
    data_dir: Path = Field(default=REPO_ROOT / "data", alias="CVM_DATA_DIR")
    artifact_dir: Path = Field(default=REPO_ROOT / "artifacts", alias="CVM_ARTIFACT_DIR")
    feature_store: Path = Field(
        default=REPO_ROOT / "data" / "processed" / "features_online.duckdb",
        alias="CVM_FEATURE_STORE",
    )

    # --- Privacy ---------------------------------------------------------
    # No default. A missing salt must fail loudly rather than silently produce
    # unsalted hashes that cannot be reconciled with a later run.
    hash_salt: str = Field(default="", alias="CVM_HASH_SALT")

    # --- MLflow ----------------------------------------------------------
    mlflow_tracking_uri: str = Field(
        default="http://localhost:5000", alias="MLFLOW_TRACKING_URI"
    )
    mlflow_experiment: str = Field(default="ai-cvm-suite", alias="MLFLOW_EXPERIMENT_NAME")

    # --- API -------------------------------------------------------------
    api_host: str = Field(default="0.0.0.0", alias="CVM_API_HOST")
    api_port: int = Field(default=8000, alias="CVM_API_PORT")
    api_url: str = Field(default="http://localhost:8000", alias="CVM_API_URL")

    # --- LLM: optional, only for channel-simulator offer copy ------------
    # The LLM writes wording from reason codes the decision engine already
    # produced. It never invents a price, a bonus or a limit. Leave the key
    # blank and the simulator falls back to templated copy.
    llm_provider: str = Field(default="groq", alias="LLM_PROVIDER")
    llm_model: str = Field(default="llama-3.3-70b-versatile", alias="LLM_MODEL")
    llm_temperature: float = Field(default=0.0, alias="LLM_TEMPERATURE")
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    hf_token: str = Field(default="", alias="HUGGINGFACEHUB_API_TOKEN")

    # --- Dataset access --------------------------------------------------
    kaggle_username: str = Field(default="", alias="KAGGLE_USERNAME")
    kaggle_key: str = Field(default="", alias="KAGGLE_KEY")

    @field_validator("hash_salt")
    @classmethod
    def _reject_placeholder_salt(cls, v: str) -> str:
        if v.startswith("CHANGE_ME"):
            raise ValueError(
                "CVM_HASH_SALT is still the placeholder from .env.example. "
                "Generate one: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        return v

    def require_salt(self) -> str:
        """Return the hash salt, failing loudly if it is missing.

        Call this at the point of hashing rather than at import, so that code
        paths which never touch an identifier (the UI, the docs build) do not
        need a salt configured.
        """
        if not self.hash_salt:
            raise RuntimeError(
                "CVM_HASH_SALT is not set. No identifier may be hashed without it -- "
                "an unsalted hash cannot be reconciled across runs and weakens "
                "the privacy commitment in the proposal, section 6.5."
            )
        return self.hash_salt


settings = Settings()


def _interpolate_env(value: Any) -> Any:
    """Resolve ``${oc.env:VAR,default}`` placeholders inside loaded YAML.

    The conf files use the OmegaConf spelling so that they stay compatible if
    the project later adopts Hydra, but we resolve them here to avoid taking
    the dependency for what is a dozen substitutions.
    """
    if isinstance(value, dict):
        return {k: _interpolate_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_interpolate_env(v) for v in value]
    if isinstance(value, str):

        def sub(m: re.Match[str]) -> str:
            return os.environ.get(m.group(1), m.group(2) or "")

        return _ENV_INTERP.sub(sub, value)
    return value


@functools.lru_cache(maxsize=None)
def load_conf(name: str) -> dict[str, Any]:
    """Load ``conf/<name>.yaml``. Nested configs use a slash: ``models/m1_churn``.

    Cached, because guardrail lookups happen per decision and a decision engine
    that re-reads YAML per subscriber would blow the 200 ms p95 budget.
    """
    path = CONF_DIR / f"{name}.yaml"
    if not path.exists():
        available = sorted(p.relative_to(CONF_DIR).as_posix() for p in CONF_DIR.rglob("*.yaml"))
        raise FileNotFoundError(f"No config {path}. Available: {available}")
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return _interpolate_env(raw)


def guardrail(config_name: str, *keys: str) -> Any:
    """Fetch a nested guardrail value, with an error that names the missing key.

    ``guardrail("pricing", "guardrails", "margin_floor", "min_margin") -> 0.15``

    A typo in a guardrail path must not silently return ``None`` and disable
    the guardrail, so this raises instead.
    """
    node: Any = load_conf(config_name)
    trail: list[str] = []
    for key in keys:
        trail.append(key)
        if not isinstance(node, dict) or key not in node:
            raise KeyError(f"conf/{config_name}.yaml has no path {'.'.join(trail)}")
        node = node[key]
    return node


def seed_everything(seed: int | None = None) -> int:
    """Seed every RNG we use. Reproducibility is a deliverable, not a nicety.

    Returns the seed actually applied so callers can log it to MLflow.
    """
    import random

    import numpy as np

    seed = settings.random_seed if seed is None else seed
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)

    try:  # optional: only present in the dl extra
        import tensorflow as tf

        tf.random.set_seed(seed)
    except ImportError:
        pass
    try:  # optional: pulled in by sdv / sentence-transformers
        import torch

        torch.manual_seed(seed)
    except ImportError:
        pass

    return seed
