import pytest

from support_bot.config import Settings
from support_bot.i18n import detect_language
from support_bot.llm.client import LLMError
from support_bot.llm.prompts import NO_ANSWER
from support_bot.orchestrator import Orchestrator
from support_bot.slack.handlers import MessageHandler, clean_text
from support_bot.storage.db import Database
from tests.fakes import FakeLLM, FakeSlackClient, call_response, text_response
from tests.test_orchestrator import StubRetriever, chunk

BOT = "UBOT"


@pytest.fixture
def db() -> Database:
    return Database(":memory:")


def make(db, responses, **settings_kwargs):
    llm = FakeLLM(responses)
    orchestrator = Orchestrator(llm, StubRetriever([chunk(1, 0.9)]), 0.5)  # type: ignore[arg-type]
    handler = MessageHandler(orchestrator, db, Settings(**settings_kwargs))
    return handler, llm, FakeSlackClient()


def event(text: str, **extra):
    return {"type": "message", "channel": "D1", "user": "U1", "ts": "1.0", "text": text, **extra}


def search():
    return call_response("search_docs", {"query": "vpn"})


def test_replies_in_thread_with_cited_answer(db) -> None:
    handler, _, slack = make(db, [search(), text_response("Use the VPN portal [1].")])
    handler.handle(event(f"<@{BOT}> how do I use the VPN?"), slack, BOT)
    assert slack.posted == [
        {
            "channel": "D1",
            "thread_ts": "1.0",
            "text": "Use the VPN portal [1].\n\n*Sources:*\n[1] VPN Access > Section 1",
        }
    ]


def test_keeps_existing_thread(db) -> None:
    handler, _, slack = make(db, [search(), text_response("ok [1]")])
    handler.handle(event("question", thread_ts="0.5"), slack, BOT)
    assert slack.posted[0]["thread_ts"] == "0.5"


def test_ignores_bot_and_subtype_messages(db) -> None:
    handler, llm, slack = make(db, [])
    handler.handle(event("hi", bot_id="B1"), slack, BOT)
    handler.handle(event("hi", user=BOT), slack, BOT)
    handler.handle(event("hi", subtype="message_changed"), slack, BOT)
    assert slack.posted == [] and llm.calls == []


def test_rejects_too_long_input_without_calling_llm(db) -> None:
    handler, llm, slack = make(db, [], max_input_chars=100)
    handler.handle(event("x" * 101), slack, BOT)
    assert llm.calls == [] and "too long" in slack.texts[0]


def test_llm_error_gives_friendly_message_in_user_language(db) -> None:
    handler, _, slack = make(db, [LLMError("boom", retryable=True, status=503)])
    handler.handle(event("não consigo acessar a VPN"), slack, BOT)
    assert "Desculpe" in slack.texts[0]


def test_unexpected_error_is_caught(db) -> None:
    handler, _, slack = make(db, [RuntimeError("bug")])
    handler.handle(event("how do I reset my password?"), slack, BOT)
    assert "something went wrong" in slack.texts[0]


def test_empty_mention_gets_help(db) -> None:
    handler, llm, slack = make(db, [])
    handler.handle(event(f"<@{BOT}>"), slack, BOT)
    assert llm.calls == [] and "status" in slack.texts[0]


def test_low_confidence_offers_ticket_draft_with_buttons(db) -> None:
    handler, _, slack = make(db, [search(), text_response(NO_ANSWER)])
    handler.handle(event("qual é o cardápio do refeitório hoje?"), slack, BOT)
    message = slack.posted[0]
    assert "chamado" in message["text"]
    buttons = message["blocks"][-1]["elements"]
    assert [b["action_id"] for b in buttons] == ["ticket_confirm", "ticket_cancel"]
    pending = db.get_pending_action(buttons[0]["value"])
    assert pending is not None and pending.user_id == "U1"
    assert pending.payload["title"] == "qual é o cardápio do refeitório hoje?"
    assert db.count_tickets() == 0  # nothing created before confirmation


def test_ticket_request_shows_model_draft(db) -> None:
    draft = {"title": "VPN SC-1020", "description": "<!channel> help", "priority": "high"}
    handler, _, slack = make(db, [call_response("create_ticket", draft)])
    handler.handle(event("open a ticket: VPN error SC-1020"), slack, BOT)
    fields = slack.posted[0]["blocks"][1]["text"]["text"]
    assert "VPN SC-1020" in fields and "high" in fields
    assert "&lt;!channel&gt;" in fields  # mention injection escaped
    assert db.count_tickets() == 0


def test_clean_text_and_language() -> None:
    assert clean_text("<@U123|bot>  hello ") == "hello"
    assert detect_language("Como faço para redefinir minha senha?") == "pt"
    assert detect_language("How do I reset my password?") == "en"
