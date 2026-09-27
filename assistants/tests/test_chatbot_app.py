from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from assistants import llm, service_client
from assistants.llm import ModelReply, ToolRequest
from tests.test_chatbot_tools import CATALOGUE, OFFER

APP = str(Path(__file__).parents[1] / "chatbot_app.py")


@pytest.fixture
def service(monkeypatch):
    """The prepaid service, faked at the client: subscriber 70016 has an approved offer."""
    asked = []

    def offer_for(base_url, key, subscriber_id):
        asked.append((key, subscriber_id))
        return OFFER if subscriber_id == "70016" else None

    monkeypatch.setattr(service_client, "health", lambda base_url: {"status": "ok"})
    monkeypatch.setattr(service_client, "catalogue", lambda base_url, key: CATALOGUE)
    monkeypatch.setattr(service_client, "offer_for", offer_for)
    return asked


@pytest.fixture
def model(monkeypatch):
    """A scripted model: asks for the offer, then repeats the tool's reason."""
    seen = []

    def complete(messages, tools):
        seen.append(messages)
        if messages[-1]["role"] == "user":
            return ModelReply(None, [ToolRequest("1", "my_offer", "{}")])
        return ModelReply(OFFER["offer_reason_en"])

    monkeypatch.setattr(llm, "groq_complete", lambda api_key=None: complete)
    return seen


def test_the_app_refuses_to_start_without_its_keys(monkeypatch, service):
    monkeypatch.delenv("PREPAID_CHURN_CHATBOT_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    app = AppTest.from_file(APP).run()
    assert not app.exception
    assert "PREPAID_CHURN_CHATBOT_KEY and GROQ_API_KEY" in app.error[0].value
    assert app.title[0].value == "Almadar packages and offers"


def test_a_signed_in_customer_gets_their_approved_offer(monkeypatch, service, model):
    monkeypatch.setenv("PREPAID_CHURN_CHATBOT_KEY", "chatbot-key-for-tests")
    monkeypatch.setenv("GROQ_API_KEY", "not-used-by-the-fake")
    app = AppTest.from_file(APP).run()
    app.text_input[0].set_value("70016").run()
    app.chat_input[0].set_value("Is there an offer for me?").run()
    assert not app.exception
    assert service == [("chatbot-key-for-tests", "70016")]
    replies = [m for m in app.chat_message if m.name == "assistant"]
    assert replies[0].markdown[0].value == OFFER["offer_reason_en"]
    panels = [c for c in replies[0].children.values() if c.type == "status"]
    assert panels[0].label.startswith("What I looked up (1)")
    # The model never received the subscriber ID.
    assert "70016" not in str(model)


def test_signing_in_as_someone_else_starts_a_new_conversation(monkeypatch, service, model):
    monkeypatch.setenv("PREPAID_CHURN_CHATBOT_KEY", "chatbot-key-for-tests")
    monkeypatch.setenv("GROQ_API_KEY", "not-used-by-the-fake")
    app = AppTest.from_file(APP).run()
    app.text_input[0].set_value("70016").run()
    app.chat_input[0].set_value("Is there an offer for me?").run()
    app.text_input[0].set_value("70017").run()
    assert [m for m in app.chat_message] == []


def test_an_arabic_reply_is_laid_out_right_to_left(monkeypatch, service):
    monkeypatch.setenv("PREPAID_CHURN_CHATBOT_KEY", "chatbot-key-for-tests")
    monkeypatch.setenv("GROQ_API_KEY", "not-used-by-the-fake")

    def complete(messages, tools):
        if messages[-1]["role"] == "user":
            return ModelReply(None, [ToolRequest("1", "my_offer", "{}")])
        return ModelReply("- عندك عرض الصبح من 06:00 إلى 11:00")

    monkeypatch.setattr(llm, "groq_complete", lambda api_key=None: complete)
    app = AppTest.from_file(APP).run()
    app.text_input[0].set_value("70016").run()
    app.chat_input[0].set_value("في عرض ليا؟").run()
    user, reply = [m.markdown[0].value for m in app.chat_message]
    assert user.startswith('<div dir="rtl">') and reply.startswith('<div dir="rtl">')
