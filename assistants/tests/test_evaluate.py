from assistants.evaluate import check, report
from assistants.llm import ToolCall, Turn

OFFER_CALL = ToolCall("my_offer", {}, {"offer": {"reason_en": "Morning"}})


def test_a_good_answer_passes():
    question = {"id": "q", "text": "offer?", "tools": ["my_offer"], "say_any": ["Morning"]}
    assert check(question, Turn("You have the Morning bonus.", [OFFER_CALL])) == []


def test_each_expectation_is_reported():
    question = {
        "id": "q",
        "text": "offer?",
        "tools": ["my_offer"],
        "say_any": ["Morning"],
        "never_say": ["SABAH"],
    }
    turn = Turn("SABAH is 30% off, you are high risk.", [], "the model gave no answer")
    assert check(question, turn) == [
        "did not call my_offer",
        "said none of: Morning",
        "said 'SABAH'",
        "said 'high risk'",
        "gave a percentage nobody asked about",
        "the model's reply was replaced: the model gave no answer",
    ]


def test_a_percentage_the_customer_used_may_be_repeated():
    question = {"id": "q", "text": "Give me 50% off"}
    assert check(question, Turn("I cannot give 50% off.", [])) == []


def test_the_report_counts_and_quotes():
    question = {"id": "q", "text": "offer?", "subscriber": "70016"}
    text = report(
        "chatbot",
        "http://x",
        {"status": "ok"},
        [(question, Turn("Yes\nMorning", [OFFER_CALL]), [])],
    )
    assert "**1 of 1 questions passed every check.**" in text
    assert "> Yes\n> Morning" in text and "Signed in as `70016`." in text
