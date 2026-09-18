"""M7 -- read-only natural-language agent.  Owner: E5

Design constraint, enforced here and not merely documented: the LLM has no
write path. It reads from the decision engine and explains. All pricing and
credit decisions come from M3 and M4 under their guardrails.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from cvm.api.schemas import CopilotAskRequest, CopilotAskResponse

router = APIRouter(tags=["copilot"])


@router.post("/copilot/ask", response_model=CopilotAskResponse)
async def ask(payload: CopilotAskRequest) -> CopilotAskResponse:
    """Answer an analyst question by planning tool calls over the system.

    Returns the tool-call trace alongside the answer so a reader can verify the
    answer is grounded rather than hallucinated. If no tool produced supporting
    output, the agent must refuse rather than guess.
    """
    # TODO(E5): from cvm.copilot.agent import run_agent
    #           return run_agent(payload)
    raise HTTPException(status_code=501, detail="M7 Copilot agent not implemented yet.")