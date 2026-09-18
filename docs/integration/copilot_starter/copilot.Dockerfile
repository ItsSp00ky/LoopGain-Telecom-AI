# M7 — CVM Copilot. LangChain agent over DuckDB, the model API, and a RAG
# retriever across model cards and the data dictionary.
#
# Inference is hosted (Groq / OpenRouter / HF Inference), so this image needs
# no GPU and no local LLM weights. It does carry a small sentence-transformer
# for embeddings, which is why it is a separate image from ui.Dockerfile.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    HF_HOME=/app/.cache/huggingface \
    ANONYMIZED_TELEMETRY=False

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/

# CPU-only torch first, or sentence-transformers drags in the CUDA runtime.
RUN pip install --upgrade pip \
 && pip install torch --index-url https://download.pytorch.org/whl/cpu \
 && pip install ".[copilot,ui]"

COPY apps/ ./apps/
COPY conf/ ./conf/

RUN useradd --create-home --uid 1000 cvm \
 && mkdir -p /app/.chroma /app/.cache/huggingface \
 && chown -R cvm:cvm /app
USER cvm

EXPOSE 8503

HEALTHCHECK --interval=20s --timeout=5s --start-period=60s --retries=5 \
  CMD curl -fsS http://localhost:8503/_stcore/health || exit 1

CMD ["streamlit", "run", "apps/copilot_ui/Home.py", \
     "--server.port=8503", "--server.address=0.0.0.0", "--server.headless=true"]
