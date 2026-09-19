# ---------------------------------------------------------------------------
# Layer 6 -- the prediction and decision API.  Deliverable D1.
#
#   docker compose up api
#
# CPU-ONLY AND DELIBERATELY SO. Every model in this branch trains and serves on
# CPU: gradient boosting, Cox, BG/NBD, a two-model uplift difference. Nothing
# here needs CUDA.
#
# The `gan` extra is NOT installed -- synthesis is a build-time step producing
# data/synthetic/population.parquet, and it has no business in a container that
# answers requests. It would pull torch.
#
# The first build installed the `ml` extra and measured 3.68 GB: 454 MB of
# NVIDIA CUDA runtime (xgboost declares `nvidia-nccl-cu12` on Linux, and nccl
# is multi-GPU collective communication a CPU booster never calls), plus
# catboost at 269 MB, xgboost at 228 MB and llvmlite at 173 MB. Exporting the
# equivalent UI layer crashed the Docker engine twice.
#
# None of it is needed to SERVE. catboost, xgboost, scikit-survival, optuna,
# statsmodels and scikit-uplift build the benchmark; nothing loads or calls
# them to answer a request. This image installs the `serve` extra instead --
# sklearn and lightgbm to load the artefacts, shap for the explanations, pulp
# for the LP, lifelines and lifetimes because the registry deserialises a Cox
# fit and two BG/NBD fits.
# ---------------------------------------------------------------------------

FROM python:3.11-slim-bookworm AS base

# libgomp1 is LightGBM's OpenMP runtime. Without it `import lightgbm` fails at
# load time with a bare "libgomp.so.1: cannot open shared object file", which
# reads like a Python problem and is a missing system package.
RUN apt-get update \
    && apt-get install --no-install-recommends -y libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# ---------------------------------------------------------------------------
# Dependencies first, source second. Docker caches per layer, so putting the
# source copy last means editing a module rebuilds one fast layer instead of
# reinstalling scikit-survival every time.
# ---------------------------------------------------------------------------
FROM base AS deps

COPY pyproject.toml README.md LICENSE ./
# setuptools needs the package tree to exist to resolve the project, but not
# its contents -- a stub keeps this layer independent of the real source.
RUN mkdir -p src/cvm && touch src/cvm/__init__.py

RUN pip install --upgrade pip \
    && pip install ".[serve]"

# Prove the serving path imports before the image is tagged, so a missing
# dependency fails the BUILD rather than the first request of the demo.
RUN python -c "import lightgbm, sklearn, shap, pulp, lifelines, lifetimes; print('serving deps ok')"

# ---------------------------------------------------------------------------
FROM deps AS runtime

COPY src/ ./src/
COPY conf/ ./conf/
RUN pip install --no-deps -e .

# NOT ROOT. A container that serves HTTP and mounts the host's data directory
# should not be able to write to it as root.
RUN useradd --create-home --uid 10001 cvm \
    && mkdir -p /app/data /app/artifacts \
    && chown -R cvm:cvm /app
USER cvm

ENV CVM_ENV=demo \
    CVM_DATA_DIR=/app/data \
    CVM_ARTIFACT_DIR=/app/artifacts \
    CVM_API_PORT=8000

EXPOSE 8000

# The compose healthcheck polls /health, which reports "ok" only when every
# model artefact is loaded AND the feature store is readable. A container that
# starts but serves a degraded API is visible rather than silently wrong.
HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

# One worker. The models load once at startup into process memory, so a second
# worker doubles the footprint for a demo that serves one person at a time --
# and the 200 ms p95 budget is met at 37 ms with one.
CMD ["uvicorn", "cvm.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
