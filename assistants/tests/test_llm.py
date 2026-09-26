import json

from assistants.llm import (
    MAX_TOOL_ROUNDS,
    ModelReply,
    ModelUnavailable,
    Tool,
    ToolRequest,
    run_turn,
)
from assistants.service_client import ServiceError


def scripted(*replies):
    """A fake model that answers with the given replies in order and records what it saw."""
    seen = []
    queue = list(replies)

    def complete(messages, tools):
        seen.append((json.loads(json.dumps(messages)), tools))
        reply = queue.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    complete.seen = seen
    return complete


def call(name, arguments="{}", id="1"):
    return ModelReply(None, [ToolRequest(id, name, arguments)])


def price_tool(result=None, error=None):
    def run(offer_id=None):
        if error:
            raise error
        return result or {"offer_id": offer_id, "price_lyd": 5.0}

    return Tool(
        "price",
        "Price of a package.",
        {"type": "object", "properties": {"offer_id": {"type": "string"}}},
        run,
    )


def fallback(calls, user_text):
    return f"fallback after {len(calls)} calls"


def test_a_grounded_answer_is_kept_with_its_trace():
    complete = scripted(call("price", '{"offer_id": "WK_1"}'), ModelReply("It costs 5 LYD."))
    turn = run_turn("rules", [], "price of WK_1?", [price_tool()], complete, fallback)
    assert turn.reply == "It costs 5 LYD."
    assert turn.replaced_because is None
    assert [(c.name, c.arguments, c.result["price_lyd"]) for c in turn.calls] == [
        ("price", {"offer_id": "WK_1"}, 5.0)
    ]
    messages, tools = complete.seen[1]
    assert messages[0] == {"role": "system", "content": "rules"}
    assert messages[-1]["role"] == "tool" and json.loads(messages[-1]["content"])["price_lyd"] == 5
    assert tools[0]["function"]["name"] == "price"


def test_an_invented_number_is_replaced_by_the_fallback():
    complete = scripted(call("price", '{"offer_id": "WK_1"}'), ModelReply("It costs 4 LYD."))
    turn = run_turn("rules", [], "price?", [price_tool()], complete, fallback)
    assert turn.reply == "fallback after 1 calls"
    assert "4" in turn.replaced_because


def test_numbers_from_earlier_checked_replies_are_allowed():
    history = [
        {"role": "user", "content": "price of WK_1?"},
        {"role": "assistant", "content": "It costs 5 LYD."},
    ]
    turn = run_turn("rules", history, "say it again", [], scripted(ModelReply("5 LYD.")), fallback)
    assert turn.reply == "5 LYD."


def test_tool_failures_become_results_the_model_can_report():
    unavailable = price_tool(error=ServiceError("down", 503))
    complete = scripted(call("price"), ModelReply("The service is not available right now."))
    turn = run_turn("rules", [], "price?", [unavailable], complete, fallback)
    assert turn.calls[0].result["error"] == "The service is not available right now."
    assert turn.replaced_because is None


def test_bad_requests_never_reach_the_tool():
    complete = scripted(
        call("price", "not json", id="a"),
        call("nothing", "{}", id="b"),
        call("price", '{"subscriber_id": "70016"}', id="c"),
        ModelReply("Sorry."),
    )
    ran = []
    tool = Tool("price", "", {"type": "object", "properties": {}}, lambda: ran.append(1) or {})
    turn = run_turn("rules", [], "q", [tool], complete, fallback)
    errors = [c.result["error"] for c in turn.calls]
    assert errors == [
        "The arguments were not valid JSON.",
        "There is no tool called 'nothing'.",
        "Unknown arguments: subscriber_id.",
    ]
    assert ran == []


def test_a_model_that_keeps_calling_tools_is_stopped():
    replies = [call("price", id=str(i)) for i in range(MAX_TOOL_ROUNDS + 1)]
    turn = run_turn("rules", [], "q", [price_tool()], scripted(*replies), fallback)
    assert turn.replaced_because == "the model kept calling tools"
    assert len(turn.calls) == MAX_TOOL_ROUNDS + 1


def test_an_unavailable_model_gets_the_fallback():
    turn = run_turn("rules", [], "q", [], scripted(ModelUnavailable("429")), fallback)
    assert turn.reply == "fallback after 0 calls"
    assert turn.replaced_because == "the language model is unavailable (429)"


def test_an_empty_reply_gets_the_fallback():
    turn = run_turn("rules", [], "q", [], scripted(ModelReply("  ")), fallback)
    assert turn.replaced_because == "the model gave no answer"


def test_a_phone_number_is_never_repeated_even_from_the_user():
    complete = scripted(ModelReply("Your number 0912345678 has no offer."))
    turn = run_turn("rules", [], "My number is 0912345678", [], complete, fallback)
    assert turn.replaced_because == "the reply held a phone number"


def test_digits_inside_identifiers_are_not_figures():
    offer = Tool("offer", "", {"type": "object", "properties": {}}, lambda: {"offer_id": "SABAH_1"})
    complete = scripted(call("offer"), ModelReply("Valid for 1 day."))
    turn = run_turn("rules", [], "offer?", [offer], complete, fallback)
    assert turn.replaced_because == "the reply had numbers no tool returned: 1"
