"""The create_ticket confirmation flow: drafts are only written after Confirm."""

import pytest

from support_bot.config import Settings
from support_bot.slack.handlers import ActionHandler
from support_bot.storage.db import Database
from tests.fakes import FakeSlackClient


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def db(clock: Clock) -> Database:
    return Database(":memory:", clock=clock)


def draft(db: Database, user: str = "U1", ttl: float = 900):
    return db.create_pending_action(
        action="create_ticket",
        payload={
            "title": "Printer jam",
            "description": "PRN-1",
            "priority": "medium",
            "lang": "en",
        },
        user_id=user,
        channel_id="C1",
        thread_ts="1.0",
        request_id="req-1",
        ttl_seconds=ttl,
    )


def click(handler: ActionHandler, slack, pending_id: str, action: str, user: str = "U1") -> None:
    body = {
        "actions": [{"action_id": action, "value": pending_id}],
        "user": {"id": user},
        "channel": {"id": "C1"},
        "message": {"ts": "2.0"},
    }
    handler.handle_ticket_action(body, slack)


def test_confirm_creates_exactly_one_ticket(db: Database) -> None:
    pending = draft(db)
    handler, slack = ActionHandler(db, Settings()), FakeSlackClient()
    click(handler, slack, pending.id, "ticket_confirm")
    click(handler, slack, pending.id, "ticket_confirm")  # double click / retry
    assert db.count_tickets() == 1
    assert "INC-000001" in slack.updated[0]["text"]
    assert "already" in slack.updated[1]["text"]
    assert slack.updated[0]["blocks"][0]["type"] == "section"  # buttons removed


def test_cancel_creates_nothing(db: Database) -> None:
    pending = draft(db)
    handler, slack = ActionHandler(db, Settings()), FakeSlackClient()
    click(handler, slack, pending.id, "ticket_cancel")
    click(handler, slack, pending.id, "ticket_confirm")
    assert db.count_tickets() == 0
    assert "cancelled" in slack.updated[0]["text"]


def test_expired_draft_cannot_be_confirmed(db: Database, clock: Clock) -> None:
    pending = draft(db, ttl=60)
    clock.now += 61
    handler, slack = ActionHandler(db, Settings()), FakeSlackClient()
    click(handler, slack, pending.id, "ticket_confirm")
    assert db.count_tickets() == 0
    assert "expired" in slack.updated[0]["text"]
    assert db.get_pending_action(pending.id).status == "expired"


def test_only_requester_can_confirm(db: Database) -> None:
    pending = draft(db, user="U1")
    handler, slack = ActionHandler(db, Settings()), FakeSlackClient()
    click(handler, slack, pending.id, "ticket_confirm", user="U2")
    assert db.count_tickets() == 0
    assert slack.ephemeral[0]["user"] == "U2"
    assert db.get_pending_action(pending.id).status == "pending"


def test_unknown_draft(db: Database) -> None:
    handler, slack = ActionHandler(db, Settings()), FakeSlackClient()
    click(handler, slack, "does-not-exist", "ticket_confirm")
    assert "couldn't find" in slack.updated[0]["text"]


def test_ticket_stores_requester_and_context(db: Database) -> None:
    pending = draft(db)
    _, status, ticket = db.confirm_ticket_action(pending.id)
    assert status == "ok" and ticket is not None
    row = db.query("SELECT * FROM tickets WHERE id = ?", (ticket.id,))[0]
    assert row["slack_user_id"] == "U1" and row["channel_id"] == "C1"
    assert row["request_id"] == "req-1" and row["priority"] == "medium"


def test_cleanup_removes_expired_and_old_resolved(db: Database, clock: Clock) -> None:
    expired = draft(db, ttl=60)
    resolved = draft(db)
    db.cancel_pending_action(resolved.id)
    alive = draft(db, ttl=10_000)
    clock.now += 120
    assert db.cleanup_expired(keep_resolved_seconds=3600)["pending_actions"] == 1
    assert db.get_pending_action(expired.id) is None
    assert db.get_pending_action(resolved.id) is not None
    clock.now += 3600
    db.cleanup_expired(keep_resolved_seconds=3600)
    assert db.get_pending_action(resolved.id) is None
    assert db.get_pending_action(alive.id) is not None


def test_schema_version_and_migrations_are_idempotent(tmp_path) -> None:
    path = tmp_path / "bot.db"
    first = Database(path)
    version = first.schema_version()
    first.close()
    second = Database(path)
    assert second.schema_version() == version >= 1
    assert len(second.query("SELECT * FROM schema_version")) == version
