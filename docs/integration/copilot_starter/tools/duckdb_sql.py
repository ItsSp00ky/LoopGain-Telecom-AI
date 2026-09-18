"""DuckDB SQL tool -- query the feature store for a cohort.

READ-ONLY at the connection level, plus a statement denylist as a second layer.
Belt and braces is appropriate here: this is the only tool with any theoretical
path to mutating state, and an LLM composing SQL is exactly the situation where
a single defence is not enough.
"""

from __future__ import annotations

FORBIDDEN = ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "ATTACH", "COPY")


def validate_sql(sql: str) -> None:
    """Reject anything that is not a plain SELECT. Raises on violation."""
    raise NotImplementedError("TODO(E5)")


def run_query(sql: str, max_rows: int = 5000):
    raise NotImplementedError("TODO(E5)")


def build_tool():
    """LangChain Tool wrapper, with the feature-store schema in its description
    so the agent writes valid SQL on the first attempt."""
    raise NotImplementedError("TODO(E5)")