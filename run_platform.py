#!/usr/bin/env python3
"""Start every backend and the shared Streamlit shell with one command.

    python3 run_platform.py

Each module keeps its own process, port and (for GIS and churn) its own `uv`
virtual environment - this script does not merge them, it only starts and stops
them together, the lowest-risk option given no module in this project uses
Docker. GIS and the KPI forecast start unconditionally: neither needs a secret.
Churn's API and the two assistants need PREPAID_CHURN_CHATBOT_KEY and
PREPAID_CHURN_COPILOT_KEY (matching keys of at least 24 characters, see
prepaid_churn/src/prepaid_churn/api.py) and are skipped with an explanatory
message if those are not set, rather than crashing the whole launch. Keys not set
in the terminal are read from assistants/.env (git-ignored), the same file and the
same rule the assistants use: a variable already set in the terminal wins.

Ports (fixed so they never collide): GIS API 8001, KPI API 8002, churn API 8000,
churn's own demo app 8501, chatbot 8503, copilot 8502, this shell 8510, mobile summary 8511.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CHATBOT_KEY_VAR = "PREPAID_CHURN_CHATBOT_KEY"
COPILOT_KEY_VAR = "PREPAID_CHURN_COPILOT_KEY"


def load_assistants_env():
    """Fill missing keys from assistants/.env so every service sees the same ones."""
    env_file = ROOT / "assistants" / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        name, value = name.strip(), value.strip().strip('"').strip("'")
        if name and not name.startswith("#") and value and name not in os.environ:
            os.environ[name] = value


def churn_keys_present() -> bool:
    return bool(os.environ.get(CHATBOT_KEY_VAR)) and bool(os.environ.get(COPILOT_KEY_VAR))


def always_on_services() -> list[dict]:
    return [
        {
            "name": "GIS API",
            "url": "http://127.0.0.1:8001",
            "cwd": ROOT / "antenna_cell_placement",
            "cmd": ["uv", "run", "--extra", "research", "uvicorn", "--app-dir", "src",
                    "antenna_cell_placement.api:app", "--port", "8001"],
        },
        {
            "name": "KPI API",
            "url": "http://127.0.0.1:8002",
            "cwd": ROOT / "network_kpi_prediction",
            "cmd": [sys.executable, "-m", "uvicorn", "api:app", "--port", "8002"],
        },
        {
            "name": "Mobile summary API",
            "url": "http://127.0.0.1:8511",
            "cwd": ROOT / "platform_app",
            "cmd": [sys.executable, "-m", "uvicorn", "mobile_summary:app",
                    "--host", "0.0.0.0", "--port", "8511"],
        },
        {
            "name": "Platform shell",
            "url": "http://127.0.0.1:8510",
            "cwd": ROOT / "platform_app",
            "cmd": [sys.executable, "-m", "streamlit", "run", "Home.py",
                    "--server.port", "8510", "--server.headless", "true"],
        },
    ]


def churn_services() -> list[dict]:
    return [
        {
            "name": "Churn API",
            "url": "http://127.0.0.1:8000",
            "cwd": ROOT / "prepaid_churn",
            "cmd": ["uv", "run", "churn", "serve"],
        },
        {
            "name": "Churn demo app",
            "url": "http://127.0.0.1:8501",
            "cwd": ROOT / "prepaid_churn",
            "cmd": ["uv", "run", "streamlit", "run", "app/Home.py",
                    "--server.port", "8501", "--server.headless", "true"],
        },
        {
            "name": "Customer chatbot",
            "url": "http://127.0.0.1:8503",
            "cwd": ROOT / "assistants",
            "cmd": ["uv", "run", "streamlit", "run", "chatbot_app.py",
                    "--server.port", "8503", "--server.headless", "true"],
        },
        {
            "name": "Employee copilot",
            "url": "http://127.0.0.1:8502",
            "cwd": ROOT / "assistants",
            "cmd": ["uv", "run", "streamlit", "run", "copilot_app.py",
                    "--server.port", "8502", "--server.headless", "true"],
        },
    ]


def main():
    load_assistants_env()
    services = always_on_services()
    if churn_keys_present():
        services += churn_services()
    else:
        print(
            f"Skipping Customer Churn API, its demo app and both assistants: "
            f"set {CHATBOT_KEY_VAR} and {COPILOT_KEY_VAR} to enable them "
            "(see assistants/README.md)."
        )

    processes = []
    try:
        for service in services:
            print(f"Starting {service['name']} on {service['url']} ...")
            processes.append((service, subprocess.Popen(service["cmd"], cwd=service["cwd"])))
            time.sleep(1)

        print("\nAll requested services are starting. URLs:")
        for service, _ in processes:
            print(f"  {service['name']:<20} {service['url']}")
        print("\nOpen the Platform shell to start: http://127.0.0.1:8510")
        print("Press Ctrl+C to stop everything.\n")

        for _, process in processes:
            process.wait()
    except KeyboardInterrupt:
        print("\nStopping all services...")
    finally:
        for service, process in processes:
            if process.poll() is None:
                process.send_signal(signal.SIGTERM if os.name != "nt" else signal.SIGBREAK)
        for service, process in processes:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
