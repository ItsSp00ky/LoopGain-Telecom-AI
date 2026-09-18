"""RAG retriever tool -- vector search over the project's own documentation.

Corpus: model cards, the data dictionary, the architecture doc, and the pricing
and advance guardrail configs. This is what lets the agent answer "why did this
subscriber get a 15 LYD limit instead of 25?" by citing the actual rule rather
than inventing a plausible one.

Descoping ladder step 2 removes this layer; the agent keeps SQL and model-API.
"""

from __future__ import annotations


def build_tool():
    raise NotImplementedError("TODO(E5)")