"""Settings from `assistants/.env`, so the keys survive a new terminal.

The file is git-ignored; `.env.example` lists what goes in it.
A variable already set in the environment wins over the file, and an empty value in the
file (a key not pasted yet) sets nothing.
"""

import os
from pathlib import Path

ENV_FILE = Path(__file__).parents[2] / ".env"


def load(path: Path | None = None) -> None:
    """Copy `NAME=value` lines from the file into the environment, without overriding."""
    path = path or ENV_FILE
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip().removeprefix("export ").strip()
        value = value.strip().strip("\"'")
        if name and value and name not in os.environ:
            os.environ[name] = value
