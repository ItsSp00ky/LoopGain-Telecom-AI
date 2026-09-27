"""One assistant turn: the model picks tools, the code runs them, and the reply is checked.

The model only chooses which tool to call and phrases what came back.
Every tool is plain code over a read-only source, every tool call and its result go into
the turn's trace, which the screen shows as the answer's sources, and a reply carrying a
number no tool returned is replaced before anyone reads it (`grounding`).
"""

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field

from assistants.grounding import has_phone_number, ungrounded
from assistants.service_client import ServiceError

# Groq shut down Llama 3.3 70B for free accounts on 2026-08-16 and named GPT-OSS 120B as
# its replacement; it is a production model with tool use (decision 54).
MODEL = "openai/gpt-oss-120b"

# Enough for "look something up, then look up one more thing"; a model still calling tools
# after that is looping, and the turn ends with a refusal instead.
MAX_TOOL_ROUNDS = 3


@dataclass(frozen=True)
class Tool:
    """A function the model may call; `run` receives the model's arguments as keywords."""

    name: str
    description: str
    parameters: dict
    run: Callable[..., dict]

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass(frozen=True)
class ToolRequest:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ModelReply:
    """What the model said: either tool requests or a final text."""

    content: str | None
    tool_requests: list[ToolRequest] = field(default_factory=list)


@dataclass(frozen=True)
class ToolCall:
    """One call as it happened, for the trace the screen shows under the answer."""

    name: str
    arguments: dict
    result: dict


@dataclass(frozen=True)
class Turn:
    reply: str
    calls: list[ToolCall]
    # Why the model's own reply was not used, or None when it was.
    replaced_because: str | None = None


class ModelUnavailable(RuntimeError):
    """The language model could not be reached, refused the key, or hit its rate limit."""


Complete = Callable[[list[dict], list[dict]], ModelReply]
Fallback = Callable[[list[ToolCall], str], str]


def groq_complete(api_key: str | None = None) -> Complete:
    """The production `Complete`: GPT-OSS 120B on Groq, with little and hidden reasoning.

    Low reasoning effort keeps a turn inside the free plan's 8K tokens a minute, and the
    reasoning text is left out of the response because nobody reads it.
    """
    import groq

    client = groq.Groq(api_key=api_key or os.environ.get("GROQ_API_KEY"), timeout=30)

    def complete(messages: list[dict], tools: list[dict]) -> ModelReply:
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=tools or None,
                tool_choice="auto" if tools else None,
                temperature=0,
                reasoning_effort="low",
                include_reasoning=False,
                max_completion_tokens=1500,
            )
        except groq.GroqError as error:
            raise ModelUnavailable(str(error)) from error
        message = response.choices[0].message
        requests = [
            ToolRequest(call.id, call.function.name, call.function.arguments)
            for call in message.tool_calls or []
        ]
        return ModelReply(message.content, requests)

    return complete


def _run(tool: Tool | None, request: ToolRequest) -> tuple[dict, dict]:
    """Run one requested tool; every failure becomes a result the model can report."""
    try:
        arguments = json.loads(request.arguments or "{}")
    except json.JSONDecodeError:
        return {}, {"error": "The arguments were not valid JSON."}
    if not isinstance(arguments, dict):
        return {}, {"error": "The arguments must be a JSON object."}
    if tool is None:
        return arguments, {"error": f"There is no tool called {request.name!r}."}
    allowed = set(tool.parameters.get("properties", {}))
    unknown = sorted(set(arguments) - allowed)
    if unknown:
        return arguments, {"error": f"Unknown arguments: {', '.join(unknown)}."}
    try:
        return arguments, tool.run(**arguments)
    except ServiceError as error:
        return arguments, {"error": "The service is not available right now.", "detail": str(error)}
    except (TypeError, ValueError) as error:
        return arguments, {"error": str(error)}


def _facts(value):
    """A tool result without its identifiers, whose digits ("SABAH_1") are not figures."""
    if isinstance(value, dict):
        return {k: _facts(v) for k, v in value.items() if not (k == "id" or k.endswith("_id"))}
    if isinstance(value, list):
        return [_facts(v) for v in value]
    return value


def run_turn(
    system_prompt: str,
    history: list[dict],
    user_text: str,
    tools: list[Tool],
    complete: Complete,
    fallback: Fallback,
) -> Turn:
    """Answer one user message; `history` holds earlier `{"role", "content"}` messages."""
    by_name = {tool.name: tool for tool in tools}
    schemas = [tool.schema() for tool in tools]
    messages = [{"role": "system", "content": system_prompt}, *history]
    messages.append({"role": "user", "content": user_text})
    calls: list[ToolCall] = []

    for _ in range(MAX_TOOL_ROUNDS + 1):
        try:
            reply = complete(messages, schemas)
        except ModelUnavailable as error:
            # The first line of Groq's own message says which: key, rate limit or request.
            detail = (str(error).splitlines() or [""])[0][:200]
            reason = f"the language model is unavailable ({detail})"
            return Turn(fallback(calls, user_text), calls, reason)
        if not reply.tool_requests:
            text = (reply.content or "").strip()
            # Earlier replies in the conversation were checked when they were given.
            sources = [m["content"] for m in history] + [user_text]
            invented = ungrounded(text, sources + [json.dumps(_facts(c.result)) for c in calls])
            if not text:
                return Turn(fallback(calls, user_text), calls, "the model gave no answer")
            if has_phone_number(text):
                return Turn(fallback(calls, user_text), calls, "the reply held a phone number")
            if invented:
                reason = "the reply had numbers no tool returned: " + ", ".join(sorted(invented))
                return Turn(fallback(calls, user_text), calls, reason)
            return Turn(text, calls)

        messages.append(
            {
                "role": "assistant",
                "content": reply.content or "",
                "tool_calls": [
                    {
                        "id": request.id,
                        "type": "function",
                        "function": {"name": request.name, "arguments": request.arguments},
                    }
                    for request in reply.tool_requests
                ],
            }
        )
        for request in reply.tool_requests:
            arguments, result = _run(by_name.get(request.name), request)
            calls.append(ToolCall(request.name, arguments, result))
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": request.id,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

    return Turn(fallback(calls, user_text), calls, "the model kept calling tools")
