<#
.SYNOPSIS
    Task runner for the AI CVM Suite. The Windows equivalent of the Makefile.

.EXAMPLE
    pwsh tasks.ps1 setup
    pwsh tasks.ps1 test
    pwsh tasks.ps1 up
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('help', 'setup', 'install', 'data', 'lint', 'fmt', 'test', 'test-all',
                 'guardrails', 'leakage', 'pipeline', 'api', 'ui', 'sim',
                 'mlflow', 'up', 'down', 'logs', 'build', 'clean')]
    [string]$Task = 'help',

    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
Set-Location $Root

function Section($m) { Write-Host "`n>>> $m" -ForegroundColor Cyan }
function Warn($m)    { Write-Host "!!! $m" -ForegroundColor Yellow }

function Assert-Env {
    # The stack pins 3.11. Anaconda base is usually newer, and TensorFlow,
    # scikit-survival and SDV will not resolve on 3.12+.
    $v = (python -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null)
    if ($v -ne '3.11') {
        Warn "Active Python is $v, this project needs 3.11. Run: conda activate cvm"
    }
}

switch ($Task) {

    'help' {
        Write-Host @"
AI CVM Suite - task runner

  Environment
    setup        Create the conda env (Python 3.11) and install the package
    install      Reinstall the package into the active env
    clean        Remove caches, __pycache__, .pytest_cache, .ruff_cache

  Data & pipeline
    data         Download every public dataset into data/raw and data/external
    pipeline     ingest -> synthesise -> features

  Quality
    lint         ruff check + black --check
    fmt          ruff --fix + black
    test         pytest, fast subset
    test-all     pytest, everything including slow
    guardrails   Commercial + credit-safety invariants only
    leakage      Point-in-time correctness only

  Run locally
    api          uvicorn with hot reload        http://localhost:8000/docs
    ui           Streamlit Command Center       http://localhost:8501
    sim          Channel simulator              http://localhost:8502
    mlflow       MLflow tracking server         http://localhost:5000

  Docker
    build        Build all images
    up           docker compose up
    down         docker compose down
    logs         Tail all container logs
"@
    }

    'setup' {
        Section 'Creating conda env "cvm" (Python 3.11)'
        conda env create -f environment.yml
        Write-Host @"

Done. Next:

    conda activate cvm
    Copy-Item .env.example .env       # then fill in your keys
    pre-commit install
    pwsh tasks.ps1 data

Torch note: SDV/CTGAN pulls torch. If disk space is tight, install the CPU
wheel first so you do not download ~2.5 GB of unused CUDA runtime:

    pip install torch --index-url https://download.pytorch.org/whl/cpu
"@ -ForegroundColor Green
    }

    'install'    { Assert-Env; Section 'pip install -e .[all]'; pip install -e ".[all]" }

    'data'       { Assert-Env; Section 'Downloading public datasets'; python scripts/download_data.py @Rest }

    'lint'       { Section 'ruff'; ruff check src tests apps scripts
                   Section 'black --check'; black --check src tests apps scripts }

    'fmt'        { Section 'ruff --fix'; ruff check --fix src tests apps scripts
                   Section 'black'; black src tests apps scripts }

    'test'       { Assert-Env; Section 'pytest (fast)'; pytest -m "not slow and not gpu" @Rest }
    'test-all'   { Assert-Env; Section 'pytest (all)'; pytest -m "not gpu" @Rest }
    'guardrails' { Assert-Env; Section 'Guardrail invariants'; pytest tests/guardrails -m guardrail -v --no-cov }
    'leakage'    { Assert-Env; Section 'Leakage / point-in-time checks'; pytest tests/leakage -m leakage -v --no-cov }

    'pipeline'   { Assert-Env
                   Section '1/3 ingest';      python -m cvm.ingest.run
                   Section '2/3 synthesise';  python -m cvm.synthesis.run
                   Section '3/3 features';    python -m cvm.features.run }

    'api'        { Assert-Env; Section 'API -> http://localhost:8000/docs'
                   uvicorn cvm.api.main:app --reload --host 0.0.0.0 --port 8000 }
    'ui'         { Assert-Env; streamlit run apps/command_center/Home.py --server.port 8501 }
    'sim'        { Assert-Env; streamlit run apps/channel_sim/Home.py --server.port 8502 }
    'mlflow'     { Assert-Env; mlflow server --host 0.0.0.0 --port 5000 `
                       --backend-store-uri "sqlite:///artifacts/mlflow.db" `
                       --default-artifact-root ./artifacts/mlruns }

    'build'      { Section 'docker compose build'; docker compose build @Rest }
    'up'         { Section 'docker compose up'; docker compose up @Rest }
    'down'       { docker compose down @Rest }
    'logs'       { docker compose logs -f @Rest }

    'clean' {
        Section 'Removing caches'
        Get-ChildItem -Path $Root -Include '__pycache__', '.pytest_cache', '.ruff_cache', '.mypy_cache', '.ipynb_checkpoints' `
            -Recurse -Directory -Force -ErrorAction SilentlyContinue |
            ForEach-Object { Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue }
        Get-ChildItem -Path $Root -Include '*.pyc', '.coverage', 'coverage.xml' `
            -Recurse -File -Force -ErrorAction SilentlyContinue |
            Remove-Item -Force -ErrorAction SilentlyContinue
        Write-Host 'Caches cleared. Nothing in data/ or artifacts/ was touched.' -ForegroundColor Green
    }
}
