"""Build and refresh the Chroma index over docs/ and conf/.

Re-index whenever a model card or a guardrail config changes, or the agent will
cite a rule the system no longer applies -- a worse failure than not answering,
because it looks authoritative.
"""

from __future__ import annotations

from pathlib import Path

CORPUS = (
    "docs/model_cards/",
    "docs/data_dictionary.md",
    "docs/architecture.md",
    "conf/pricing.yaml",
    "conf/advance.yaml",
)


def build_index(persist_directory: Path) -> None:
    raise NotImplementedError("TODO(E5)")


def retrieve(query: str, top_k: int = 4) -> list[dict]:
    raise NotImplementedError("TODO(E5)")