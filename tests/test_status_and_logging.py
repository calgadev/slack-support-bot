import json
import logging

from support_bot.logging_setup import configure_logging, get_logger
from support_bot.observability import hash_user_id
from support_bot.status import StatusService, format_duration, is_status_request
from support_bot.storage.db import Database, RequestRecord


class Clock:
    now = 100_000.0

    def __call__(self) -> float:
        return self.now


def record(db: Database, rid: str, outcome: str = "answered", latency: int = 1000) -> None:
    db.record_request(
        RequestRecord(id=rid, user_hash="h", channel_id="C", outcome=outcome, latency_ms=latency)
    )


def test_stats_only_cover_last_24_hours() -> None:
    clock = Clock()
    db = Database(":memory:", clock=clock)
    record(db, "old", outcome="error", latency=9000)
    clock.now += 25 * 3600
    record(db, "a", latency=1000)
    record(db, "b", outcome="error", latency=3000)
    stats = db.request_stats()
    assert (stats.requests, stats.errors, stats.avg_latency_ms) == (2, 1, 2000.0)


def test_status_render_in_portuguese_and_empty_state() -> None:
    db = Database(":memory:")
    text = StatusService(db, lambda: 0, started_at=0.0, clock=lambda: 90_061.0).render("pt")
    assert "Tempo no ar: 1d 1h 1m" in text
    assert "Requisições: 0" in text and "Latência média: n/d" in text


def test_status_survives_index_errors() -> None:
    def broken() -> int:
        raise RuntimeError("chroma down")

    text = StatusService(Database(":memory:"), broken, started_at=0.0).render("en")
    assert "Indexed chunks: n/a" in text


def test_status_detection_and_duration() -> None:
    assert is_status_request(" STATUS ") and not is_status_request("status of my ticket")
    assert format_duration(59) == "59s" and format_duration(3600) == "1h 0m"


def test_user_hash_is_stable_salted_and_not_reversible() -> None:
    assert hash_user_id("U1", "s1") == hash_user_id("U1", "s1")
    assert hash_user_id("U1", "s1") != hash_user_id("U1", "s2")
    assert "U1" not in hash_user_id("U1", "s1")


def test_logs_are_json_lines(capsys) -> None:
    configure_logging("INFO")
    get_logger("test").info("request_completed", request_id="r1", latency_ms=12)
    logging.getLogger("third.party").warning("plain stdlib message")
    lines = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]
    assert lines[0]["event"] == "request_completed" and lines[0]["request_id"] == "r1"
    assert lines[0]["level"] == "info" and "timestamp" in lines[0]
    assert lines[1]["event"] == "plain stdlib message" and lines[1]["level"] == "warning"
