# Layer 6 — prediction & decision API.
# CPU-only. Target: p95 < 200 ms on one container for tabular endpoints.
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# libgomp1 is required by LightGBM; the rest of the stack is pure wheels.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 curl \
 && rm -rf /var/lib/apt/lists/*

# Dependency layer first so source edits do not invalidate the pip cache.
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --upgrade pip \
 && pip install ".[ml,mlops]"

COPY conf/ ./conf/

# Never run as root.
RUN useradd --create-home --uid 1000 cvm \
 && mkdir -p /app/data /app/artifacts \
 && chown -R cvm:cvm /app
USER cvm

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=40s --retries=5 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "cvm.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
