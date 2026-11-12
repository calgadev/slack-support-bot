"""SQLite storage (standard library ``sqlite3``).

All tables are created here, through an ordered list of migrations tracked in the
``schema_version`` table. Add a new entry to ``MIGRATIONS`` to change the schema;
never edit an existing one.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

Clock = Callable[[], float]

MIGRATIONS: list[str] = [
    # 1: tickets and pending (human-confirmed) actions
    """
    CREATE TABLE tickets (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        title         TEXT NOT NULL,
        description   TEXT NOT NULL,
        priority      TEXT NOT NULL CHECK (priority IN ('low', 'medium', 'high', 'critical')),
        status        TEXT NOT NULL DEFAULT 'open',
        slack_user_id TEXT NOT NULL,
        channel_id    TEXT NOT NULL,
        thread_ts     TEXT,
        request_id    TEXT,
        created_at    REAL NOT NULL
    );
    CREATE TABLE pending_actions (
        id           TEXT PRIMARY KEY,
        action       TEXT NOT NULL,
        payload      TEXT NOT NULL,
        user_id      TEXT NOT NULL,
        channel_id   TEXT NOT NULL,
        thread_ts    TEXT,
        request_id   TEXT,
        status       TEXT NOT NULL DEFAULT 'pending',
        created_at   REAL NOT NULL,
        expires_at   REAL NOT NULL
    );
    CREATE INDEX idx_pending_expires ON pending_actions (expires_at);
    """,
]

PendingStatus = Literal["pending", "confirmed", "cancelled", "expired"]


@dataclass(frozen=True)
class PendingAction:
    id: str
    action: str
    payload: dict[str, Any]
    user_id: str
    channel_id: str
    thread_ts: str | None
    request_id: str | None
    status: PendingStatus
    created_at: float
    expires_at: float


@dataclass(frozen=True)
class Ticket:
    id: int
    title: str
    description: str
    priority: str
    status: str
    slack_user_id: str
    created_at: float

    @property
    def key(self) -> str:
        return f"INC-{self.id:06d}"


class Database:
    def __init__(self, path: Path | str, clock: Clock = time.time) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self.migrate()

    # -- infrastructure -------------------------------------------------------------

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")

    def query(self, sql: str, params: tuple[Any, ...] | dict[str, Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def schema_version(self) -> int:
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
            )
            row = self._conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
            return int(row[0] or 0)

    def migrate(self) -> None:
        current = self.schema_version()
        for version, script in enumerate(MIGRATIONS, start=1):
            if version <= current:
                continue
            with self.transaction() as conn:
                for statement in filter(str.strip, script.split(";")):
                    conn.execute(statement)
                conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- pending actions ------------------------------------------------------------

    def create_pending_action(
        self,
        *,
        action: str,
        payload: dict[str, Any],
        user_id: str,
        channel_id: str,
        thread_ts: str | None,
        request_id: str | None,
        ttl_seconds: float,
    ) -> PendingAction:
        now = self.clock()
        pending_id = uuid.uuid4().hex
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO pending_actions (id, action, payload, user_id, channel_id, thread_ts,"
                " request_id, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    pending_id,
                    action,
                    json.dumps(payload),
                    user_id,
                    channel_id,
                    thread_ts,
                    request_id,
                    now,
                    now + ttl_seconds,
                ),
            )
        found = self.get_pending_action(pending_id)
        assert found is not None
        return found

    def get_pending_action(self, pending_id: str) -> PendingAction | None:
        rows = self.query("SELECT * FROM pending_actions WHERE id = ?", (pending_id,))
        return _row_to_pending(rows[0]) if rows else None

    def _claim(
        self, conn: sqlite3.Connection, pending_id: str, new_status: PendingStatus
    ) -> tuple[PendingAction | None, str]:
        row = conn.execute("SELECT * FROM pending_actions WHERE id = ?", (pending_id,)).fetchone()
        if row is None:
            return None, "not_found"
        pending = _row_to_pending(row)
        if pending.status != "pending":
            return pending, "already_resolved"
        if pending.expires_at <= self.clock():
            conn.execute(
                "UPDATE pending_actions SET status = 'expired' WHERE id = ?", (pending_id,)
            )
            return pending, "expired"
        conn.execute("UPDATE pending_actions SET status = ? WHERE id = ?", (new_status, pending_id))
        return pending, "ok"

    def cancel_pending_action(self, pending_id: str) -> tuple[PendingAction | None, str]:
        """Returns the action and one of: ok, not_found, already_resolved, expired."""
        with self.transaction() as conn:
            return self._claim(conn, pending_id, "cancelled")

    def confirm_ticket_action(
        self, pending_id: str
    ) -> tuple[PendingAction | None, str, Ticket | None]:
        """Confirm a pending ``create_ticket`` action and insert the ticket atomically.

        The status check and the insert run in one transaction, so a double click or a
        retried interaction can never create two tickets.
        """
        with self.transaction() as conn:
            pending, result = self._claim(conn, pending_id, "confirmed")
            if result != "ok" or pending is None:
                return pending, result, None
            if pending.action != "create_ticket":
                raise ValueError(f"Unexpected action {pending.action!r}")
            payload = pending.payload
            cursor = conn.execute(
                "INSERT INTO tickets (title, description, priority, slack_user_id, channel_id,"
                " thread_ts, request_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    payload["title"],
                    payload["description"],
                    payload["priority"],
                    pending.user_id,
                    pending.channel_id,
                    pending.thread_ts,
                    pending.request_id,
                    self.clock(),
                ),
            )
            ticket_id = int(cursor.lastrowid or 0)
        return pending, "ok", self.get_ticket(ticket_id)

    # -- tickets --------------------------------------------------------------------

    def get_ticket(self, ticket_id: int) -> Ticket | None:
        rows = self.query(
            "SELECT id, title, description, priority, status, slack_user_id, created_at"
            " FROM tickets WHERE id = ?",
            (ticket_id,),
        )
        return Ticket(**dict(rows[0])) if rows else None

    def count_tickets(self) -> int:
        return int(self.query("SELECT COUNT(*) FROM tickets")[0][0])

    # -- maintenance ----------------------------------------------------------------

    def cleanup_expired(self, keep_resolved_seconds: float = 7 * 24 * 3600) -> dict[str, int]:
        """Delete expired pending actions and old resolved ones."""
        now = self.clock()
        with self.transaction() as conn:
            pending = conn.execute(
                "DELETE FROM pending_actions WHERE (status = 'pending' AND expires_at <= ?)"
                " OR (status != 'pending' AND created_at <= ?)",
                (now, now - keep_resolved_seconds),
            ).rowcount
        return {"pending_actions": pending}


def _row_to_pending(row: sqlite3.Row) -> PendingAction:
    data = dict(row)
    data["payload"] = json.loads(data["payload"])
    return PendingAction(**data)
