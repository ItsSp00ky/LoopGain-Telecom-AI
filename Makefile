# AI CVM Suite — task runner for macOS / Linux.
# Windows teammates: use `pwsh tasks.ps1 <target>` instead. Same target names.
.DEFAULT_GOAL := help
.PHONY: help setup install data lint fmt test test-all guardrails leakage \
        pipeline api ui sim mlflow build up down logs clean

help:  ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup:  ## Create the conda env (Python 3.11) and install the package
	conda env create -f environment.yml
	@echo "Now: conda activate cvm && cp .env.example .env && pre-commit install"

install:  ## Reinstall the package into the active env
	pip install -e ".[all]"

data:  ## Download every public dataset
	python scripts/download_data.py

lint:  ## ruff check + black --check
	ruff check src tests apps scripts
	black --check src tests apps scripts

fmt:  ## ruff --fix + black
	ruff check --fix src tests apps scripts
	black src tests apps scripts

test:  ## pytest, fast subset
	pytest -m "not slow and not gpu"

test-all:  ## pytest, everything except GPU
	pytest -m "not gpu"

guardrails:  ## Commercial + credit-safety invariants only
	pytest tests/guardrails -m guardrail -v --no-cov

leakage:  ## Point-in-time correctness only
	pytest tests/leakage -m leakage -v --no-cov

pipeline:  ## ingest -> synthesise -> features
	python -m cvm.ingest.run
	python -m cvm.synthesis.run
	python -m cvm.features.run

api:  ## uvicorn with hot reload
	uvicorn cvm.api.main:app --reload --host 0.0.0.0 --port 8000

ui:  ## Streamlit Command Center
	streamlit run apps/command_center/Home.py --server.port 8501

sim:  ## Channel simulator
	streamlit run apps/channel_sim/Home.py --server.port 8502

mlflow:  ## MLflow tracking server
	mlflow server --host 0.0.0.0 --port 5000 \
		--backend-store-uri sqlite:///artifacts/mlflow.db \
		--default-artifact-root ./artifacts/mlruns

build:  ## Build all Docker images
	docker compose build

up:  ## docker compose up
	docker compose up

down:  ## docker compose down
	docker compose down

logs:  ## Tail all container logs
	docker compose logs -f

clean:  ## Remove caches (leaves data/ and artifacts/ alone)
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage coverage.xml
