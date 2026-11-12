import pytest

from support_bot.config import Settings
from support_bot.i18n import detect_language
from support_bot.llm.client import LLMError
from support_bot.llm.prompts import NO_ANSWER
from support_bot.orchestrator import Orchestrator
from support_bot.slack.handlers import MessageHandler, clean_text
from support_bot.status import StatusService
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
    status = StatusService(db, lambda: 66, started_at=0.0, clock=lambda: 3_700.0)
    ids = iter(f"req-{n}" for n in range(1, 100))
    handler = MessageHandler(
        orchestrator, db, Settings(**settings_kwargs), status, request_id_factory=lambda: next(ids)
    )
    return handler, llm, FakeSlackClient()


_ts = iter(range(1, 10_000))


def event(text: str, **extra):
    base = {"type": "message", "channel": "D1", "user": "U1", "text": text}
    base["ts"] = f"{next(_ts)}.0"
    return {**base, **extra}


def search():
    return call_response("search_docs", {"query": "vpn"})


def test_replies_in_thread_with_cited_answer(db) -> None:
    handler, _, slack = make(db, [search(), text_response("Use the VPN portal [1].")])
    msg = event(f"<@{BOT}> how do I use the VPN?")
    handler.handle(msg, slack, BOT)
    [posted] = slack.posted
    assert posted["channel"] == "D1" and posted["thread_ts"] == msg["ts"]
    assert posted["text"] == "Use the VPN portal [1].\n\n*Sources:*\n[1] VPN Access > Section 1"
    buttons = posted["blocks"][-1]["elements"]
    assert [b["action_id"] for b in buttons] == ["feedback_up", "feedback_down"]
    assert buttons[0]["value"] == "req-1"


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
    blocks = {b.get("block_id"): b for b in message["blocks"]}
    buttons = blocks["ticket_confirmation"]["elements"]
    assert [b["action_id"] for b in buttons] == ["ticket_confirm", "ticket_cancel"]
    assert "feedback" in blocks  # every answer can be rated
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


def test_duplicate_events_are_processed_once(db) -> None:
    handler, llm, slack = make(db, [search(), text_response("A [1].")])
    msg = event("how do I use the VPN?", channel_type="im")
    handler.handle(msg, slack, BOT, event_id="Ev1")
    handler.handle(msg, slack, BOT, event_id="Ev1")  # Slack retry
    handler.handle({**msg, "type": "app_mention"}, slack, BOT, event_id="Ev2")  # same message
    assert len(slack.posted) == 1 and len(llm.calls) == 2


def test_status_command_reports_metrics_without_llm(db) -> None:
    handler, llm, slack = make(db, [search(), text_response("A [1].")])
    handler.handle(event("how do I use the VPN?"), slack, BOT)
    handler.handle(event(f"<@{BOT}> Status"), slack, BOT)
    status = slack.texts[-1]
    assert "Uptime: 1h 1m" in status
    assert "Indexed chunks: 66" in status
    assert "Requests: 1" in status and "Errors: 0" in status
    assert len(llm.calls) == 2  # status did not call the LLM
    assert db.request_stats().requests == 1  # status itself is not counted


def test_request_is_recorded_with_metrics(db) -> None:
    handler, _, slack = make(db, [search(), text_response("A [1].")])
    handler.handle(event("how do I use the VPN?"), slack, BOT)
    row = db.query("SELECT * FROM requests")[0]
    assert row["id"] == "req-1" and row["outcome"] == "answered"
    assert row["user_hash"] != "U1" and len(row["user_hash"]) == 16
    assert row["input_tokens"] == 20 and row["llm_calls"] == 2
    assert '"score": 0.9' in row["retrieved"] and "search_docs" in row["tool_calls"]
    assert row["error"] is None and row["latency_ms"] >= 0


def test_errors_are_recorded_and_counted(db) -> None:
    handler, _, slack = make(db, [LLMError("down", retryable=True, status=503)])
    handler.handle(event("how do I use the VPN?"), slack, BOT)
    row = db.query("SELECT outcome, error FROM requests")[0]
    assert row["outcome"] == "error" and "503" in row["error"]
    assert db.request_stats().errors == 1


def test_slack_post_failure_is_recorded(db) -> None:
    handler, _, slack = make(db, [search(), text_response("A [1].")])

    def broken(**kwargs):
        raise RuntimeError("slack down")

    slack.chat_postMessage = broken  # type: ignore[method-assign]
    handler.handle(event("how do I use the VPN?"), slack, BOT)  # must not raise
    assert db.query("SELECT outcome FROM requests")[0]["outcome"] == "error"


def test_feedback_is_stored_per_user_and_request(db) -> None:
    from support_bot.slack.handlers import ActionHandler

    handler, _, slack = make(db, [search(), text_response("A [1].")])
    handler.handle(event("how do I use the VPN?"), slack, BOT)
    actions = ActionHandler(db, Settings())

    def click(action_id: str, user: str = "U1") -> None:
        body = {
            "actions": [{"action_id": action_id, "value": "req-1"}],
            "user": {"id": user},
            "channel": {"id": "D1"},
            "message": {"ts": "9.0", "thread_ts": "1.0"},
        }
        actions.handle_feedback(body, slack)

    click("feedback_up")
    click("feedback_down")  # changes the vote, no duplicate row
    click("feedback_up", user="U2")
    rows = db.query("SELECT rating FROM feedback WHERE request_id = 'req-1' ORDER BY rating")
    assert [r["rating"] for r in rows] == ["down", "up"]
    assert "Thanks" in slack.ephemeral[0]["text"]
