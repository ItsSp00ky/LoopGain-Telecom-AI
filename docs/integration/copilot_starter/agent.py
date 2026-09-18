"""The LangChain agent.  Owner: E5

Read-only by construction: the tool set contains no write path, the DuckDB
connection is opened read-only, and the model-API tool allowlists GET/score
endpoints only. Making the agent well-behaved via the prompt would not be
enough -- prompts are advisory, connection modes are not.

Intermediate steps are returned and rendered in the UI so evaluators can see
the answer is grounded rather than hallucinated. That is a demo requirement,
not a debug flag.
"""

from __future__ import annotations

from cvm.api.schemas import CopilotAskRequest, CopilotAskResponse


def build_agent():
    """Assemble the LLM, the tools, and the read-only system prompt."""
    raise NotImplementedError("TODO(E5)")


def run_agent(payload: CopilotAskRequest) -> CopilotAskResponse:
    """Answer a question, returning the tool-call trace alongside the answer.

    If no tool produced supporting output, REFUSE rather than guess. An
    unfounded answer in the demo is worse than "I could not determine that" --
    see the risk register.
    """
    raise NotImplementedError("TODO(E5)")