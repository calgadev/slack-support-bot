from support_bot.config import Settings
from support_bot.i18n import detect_language
from support_bot.llm.client import LLMError
from support_bot.orchestrator import Orchestrator
from support_bot.slack.handlers import MessageHandler, clean_text
from tests.fakes import FakeLLM, FakeSlackClient, text_response

BOT = "UBOT"


def make(responses, **settings_kwargs):
    llm = FakeLLM(responses)
    handler = MessageHandler(Orchestrator(llm), Settings(**settings_kwargs))
    return handler, llm, FakeSlackClient()


def event(text: str, **extra):
    return {"type": "message", "channel": "D1", "user": "U1", "ts": "1.0", "text": text, **extra}


def test_replies_in_thread_with_llm_text() -> None:
    handler, _, slack = make([text_response("Use the VPN portal.")])
    handler.handle(event(f"<@{BOT}> how do I use the VPN?"), slack, BOT)
    assert slack.posted == [{"channel": "D1", "thread_ts": "1.0", "text": "Use the VPN portal."}]


def test_keeps_existing_thread() -> None:
    handler, _, slack = make([text_response("ok")])
    handler.handle(event("question", thread_ts="0.5"), slack, BOT)
    assert slack.posted[0]["thread_ts"] == "0.5"


def test_ignores_bot_and_subtype_messages() -> None:
    handler, llm, slack = make([])
    handler.handle(event("hi", bot_id="B1"), slack, BOT)
    handler.handle(event("hi", user=BOT), slack, BOT)
    handler.handle(event("hi", subtype="message_changed"), slack, BOT)
    assert slack.posted == [] and llm.calls == []


def test_rejects_too_long_input_without_calling_llm() -> None:
    handler, llm, slack = make([], max_input_chars=100)
    handler.handle(event("x" * 101), slack, BOT)
    assert llm.calls == [] and "too long" in slack.texts[0]


def test_llm_error_gives_friendly_message_in_user_language() -> None:
    handler, _, slack = make([LLMError("boom", retryable=True, status=503)])
    handler.handle(event("não consigo acessar a VPN"), slack, BOT)
    assert "Desculpe" in slack.texts[0]


def test_unexpected_error_is_caught() -> None:
    handler, _, slack = make([RuntimeError("bug")])
    handler.handle(event("how do I reset my password?"), slack, BOT)
    assert "something went wrong" in slack.texts[0]


def test_empty_mention_gets_help() -> None:
    handler, llm, slack = make([])
    handler.handle(event(f"<@{BOT}>"), slack, BOT)
    assert llm.calls == [] and "status" in slack.texts[0]


def test_clean_text_and_language() -> None:
    assert clean_text("<@U123|bot>  hello ") == "hello"
    assert detect_language("Como faço para redefinir minha senha?") == "pt"
    assert detect_language("How do I reset my password?") == "en"
