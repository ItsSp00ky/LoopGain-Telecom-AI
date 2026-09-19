# ---------------------------------------------------------------------------
# Layer 7 -- the Streamlit surfaces. Serves BOTH apps.
#
#   docker compose up ui            # Command Center, :8501
#   docker compose up channel-sim   # Channel Simulator, :8502
#
# ONE IMAGE, TWO SERVICES. The two apps share `apps/_shared.py`, the same
# config and the same model artefacts; the only difference is which script
# Streamlit runs, which compose supplies as the command. Two nearly identical
# Dockerfiles would drift.
#
# THE SCREENS READ THE ARTEFACTS DIRECTLY, not only through the API, which is
# why the `ml` extra is here. `_shared.py` loads the M1 bundle to render a SHAP
# waterfall on the Subscriber 360 screen, and the decision engine is called
# in-process for the offer and advance panels. That is a deliberate trade: the
# dashboard keeps working when the API is down, at the cost of a larger image.
# ---------------------------------------------------------------------------

FROM python:3.11-slim-bookworm AS base

# libgomp1 for LightGBM (SHAP explanations load the model), curl for the
# healthcheck against Streamlit's own endpoint.
RUN apt-get update \
    && apt-get install --no-install-recommends -y libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

FROM base AS deps

COPY pyproject.toml README.md LICENSE ./
RUN mkdir -p src/cvm && touch src/cvm/__init__.py

# `rtl` is not optional for this image whatever the extra is called: without
# arabic-reshaper and python-bidi the SMS preview draws Arabic letters in their
# isolated forms, in the wrong order. That is the one screen whose entire point
# is showing the subscriber what they actually receive.
RUN pip install --upgrade pip \
    && pip install ".[serve,ui,rtl]"

# Prove the serving path imports before the image is tagged, so a missing
# dependency fails the BUILD rather than the first request of the demo.
RUN python -c "import lightgbm, sklearn, shap, pulp, lifelines, lifetimes; print('serving deps ok')"

FROM deps AS runtime

COPY src/ ./src/
COPY conf/ ./conf/
COPY apps/ ./apps/
RUN pip install --no-deps -e .

RUN useradd --create-home --uid 10001 cvm \
    && mkdir -p /app/data /app/artifacts /home/cvm/.streamlit \
    && chown -R cvm:cvm /app /home/cvm

# Headless, no telemetry, no first-run email prompt. Without this Streamlit
# blocks on stdin asking for an email address and the container never serves.
RUN printf '[browser]\ngatherUsageStats = false\n[server]\nheadless = true\n' \
    > /home/cvm/.streamlit/config.toml \
    && chown cvm:cvm /home/cvm/.streamlit/config.toml

USER cvm

ENV CVM_ENV=demo \
    CVM_DATA_DIR=/app/data \
    CVM_ARTIFACT_DIR=/app/artifacts \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

EXPOSE 8501 8502

HEALTHCHECK --interval=20s --timeout=5s --start-period=30s --retries=5 \
    CMD curl -fsS "http://localhost:${STREAMLIT_SERVER_PORT:-8501}/_stcore/health" || exit 1

# Overridden per service in docker-compose.yml. The default is the Command
# Center so `docker run` on this image alone does something useful.
CMD ["streamlit", "run", "apps/command_center/Home.py", \
     "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
