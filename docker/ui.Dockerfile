# Layer 7a/7b — Streamlit surfaces: Command Center and Channel Simulator.
# Shared image; docker-compose supplies the `streamlit run` target per service.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends libgomp1 curl fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/
# arabic-reshaper + python-bidi so the channel simulator renders offer copy
# correctly; Streamlit draws unreshaped Arabic backwards and disconnected.
RUN pip install --upgrade pip \
 && pip install ".[ui,ml,rtl]"

COPY apps/ ./apps/
COPY conf/ ./conf/

RUN useradd --create-home --uid 1000 cvm && chown -R cvm:cvm /app
USER cvm

EXPOSE 8501 8502

HEALTHCHECK --interval=20s --timeout=5s --start-period=30s --retries=5 \
  CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "apps/command_center/Home.py", \
     "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
