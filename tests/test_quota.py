"""HTTP 429 handling: honor RetryInfo, never retry a daily quota, stop cleanly."""

from unittest.mock import MagicMock

import pytest
from google.genai import errors as genai_errors
from google.genai import types

from evals.run import GoldenItem, run_items
from support_bot.config import Settings
from support_bot.llm.client import GeminiClient, LLMError, parse_quota_error
from support_bot.orchestrator import Orchestrator
from support_bot.slack.handlers import MessageHandler
from support_bot.status import StatusService
from support_bot.storage.db import Database
from tests.fakes import FakeLLM, FakeSlackClient, call_response, text_response
from tests.test_orchestrator import StubRetriever, chunk

DAILY = "GenerateRequestsPerDayPerProjectPerModel-FreeTier"
PER_MINUTE = "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"
METRIC = "generativelanguage.googleapis.com/generate_content_free_tier_requests"


def quota_error(quota_id: str, retry_delay: str | None) -> genai_errors.ClientError:
    """A 429 shaped like the real Gemini API response (google.rpc details)."""
    details: list[dict] = [
        {"@type": "type.googleapis.com/google.rpc.Help", "links": []},
        {
            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
            "violations": [{"quotaMetric": METRIC, "quotaId": quota_id, "quotaValue": "20"}],
        },
    ]
    if retry_delay is not None:
        details.append(
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry_delay}
        )
    body = {
        "error": {
            "code": 429,
            "message": "You exceeded your current quota.",
            "status": "RESOURCE_EXHAUSTED",
            "details": details,
        }
    }
    return genai_errors.ClientError(429, body)


def ok() -> types.GenerateContentResponse:
    content = types.Content(role="model", parts=[types.Part(text="hi")])
    return types.GenerateContentResponse(candidates=[types.Candidate(content=content)])


def make_client(sleeps: list[float], max_attempts: int = 3, max_retry_delay: float = 60):
    client = GeminiClient(
        api_key="test-key",
        model="m",
        embedding_model="e",
        embedding_dim=8,
        timeout_seconds=1,
        max_attempts=max_attempts,
        retry_initial_wait=0,
        max_retry_delay=max_retry_delay,
        sleep=sleeps.append,
    )
    client._client = MagicMock()
    return client


def user() -> list[types.Content]:
    return [types.Content(role="user", parts=[types.Part.from_text(text="q")])]


def test_parse_quota_error_reads_retry_info_and_daily_quota() -> None:
    info = parse_quota_error(quota_error(DAILY, "37008s"))
    assert info is not None and info.daily and info.retry_delay == 37008.0
    assert info.quota_ids == (DAILY,)
    minute = parse_quota_error(quota_error(PER_MINUTE, "1.5s"))
    assert minute is not None and not minute.daily and minute.retry_delay == 1.5
    assert parse_quota_error(genai_errors.ServerError(503, {"error": {}})) is None


def test_parse_quota_error_tolerates_missing_or_odd_details() -> None:
    bare = parse_quota_error(genai_errors.ClientError(429, {"error": {"message": "quota"}}))
    assert bare is not None and bare.retry_delay is None and not bare.daily
    odd = genai_errors.ClientError(429, {"error": {"details": ["x", {"@type": None}]}})
    assert parse_quota_error(odd) is not None


def test_per_minute_429_waits_for_server_retry_delay() -> None:
    sleeps: list[float] = []
    client = make_client(sleeps)
    client._client.models.generate_content.side_effect = [quota_error(PER_MINUTE, "7s"), ok()]
    assert client.generate(user(), system_instruction="s").text == "hi"
    assert sleeps == [7.0]  # RetryInfo honored instead of exponential backoff


def test_daily_quota_is_not_retried_and_is_flagged() -> None:
    sleeps: list[float] = []
    client = make_client(sleeps)
    client._client.models.generate_content.side_effect = quota_error(DAILY, "37008s")
    with pytest.raises(LLMError) as info:
        client.generate(user(), system_instruction="s")
    assert client._client.models.generate_content.call_count == 1 and sleeps == []
    assert info.value.quota_exhausted and not info.value.retryable
    assert info.value.retry_after == 37008.0


def test_retry_delay_longer_than_cap_gives_up_without_waiting() -> None:
    sleeps: list[float] = []
    client = make_client(sleeps, max_retry_delay=60)
    client._client.models.generate_content.side_effect = quota_error(PER_MINUTE, "120s")
    with pytest.raises(LLMError) as info:
        client.generate(user(), system_instruction="s")
    assert client._client.models.generate_content.call_count == 1 and sleeps == []
    assert not info.value.quota_exhausted and info.value.retry_after == 120.0


def test_daily_quota_on_embeddings_is_flagged() -> None:
    client = make_client([])
    client._client.models.embed_content.side_effect = quota_error(DAILY, "100s")
    with pytest.raises(LLMError) as info:
        client.embed(["a"])
    assert info.value.quota_exhausted


def _handler(db: Database, responses: list) -> tuple[MessageHandler, FakeSlackClient]:
    retriever = StubRetriever([chunk(1, 0.9)])
    orchestrator = Orchestrator(FakeLLM(responses), retriever, 0.5)  # type: ignore[arg-type]
    status = StatusService(db, lambda: 1, started_at=0.0)
    return MessageHandler(orchestrator, db, Settings(), status), FakeSlackClient()


def _event(text: str) -> dict:
    return {"type": "message", "channel": "D1", "user": "U1", "ts": "5.0", "text": text}


def test_slack_reply_on_daily_quota_offers_ticket_draft() -> None:
    db = Database(":memory:")
    error = LLMError("quota", status=429, quota_exhausted=True, retry_after=3600)
    handler, slack = _handler(db, [error])
    handler.handle(_event("how do I reset my password?"), slack, "UBOT")
    message = slack.posted[0]
    assert "daily limit" in message["text"]
    blocks = {b.get("block_id"): b for b in message["blocks"]}
    assert "ticket_confirmation" in blocks  # the user can still reach the Service Desk
    row = db.query("SELECT outcome, error FROM requests")[0]
    assert row["outcome"] == "quota_exhausted" and "429" in row["error"]


def test_slack_reply_on_other_llm_errors_also_offers_ticket_draft() -> None:
    db = Database(":memory:")
    handler, slack = _handler(db, [LLMError("down", retryable=True, status=503)])
    handler.handle(_event("não consigo acessar a VPN"), slack, "UBOT")
    message = slack.posted[0]
    assert "rascunho" in message["text"]
    assert any(b.get("block_id") == "ticket_confirmation" for b in message["blocks"])
    assert db.query("SELECT outcome FROM requests")[0]["outcome"] == "error"


def test_eval_run_stops_cleanly_when_daily_quota_runs_out() -> None:
    items = [GoldenItem(f"q{i}", "en", True, f"question {i}", "a.md", "ref") for i in range(5)]
    daily = LLMError("quota", status=429, quota_exhausted=True)
    llm = FakeLLM([call_response("search_docs", {"query": "x"}), text_response("A [1]."), daily])
    retriever = StubRetriever([chunk(1, 0.9)])
    judge = FakeLLM([text_response('{"score": 2, "reason": "ok"}')])
    sleeps: list[float] = []
    results, aborted = run_items(
        items,
        retriever,  # type: ignore[arg-type]
        4,
        Orchestrator(llm, retriever, 0.5),  # type: ignore[arg-type]
        judge,
        delay=5,
        sleep=sleeps.append,
    )
    assert [r.id for r in results] == ["q0", "q1"]  # q2..q4 never sent
    assert results[1].quota_exhausted and aborted is not None and "2 of 5" in aborted
    assert sleeps == [5]
