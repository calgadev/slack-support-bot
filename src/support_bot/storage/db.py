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
    # 2: observability (requests), answer feedback and event de-duplication
    """
    CREATE TABLE requests (
        id             TEXT PRIMARY KEY,
        created_at     REAL NOT NULL,
        user_hash      TEXT NOT NULL,
        channel_id     TEXT NOT NULL,
        lang           TEXT,
        outcome        TEXT NOT NULL,
        model          TEXT,
        latency_ms     INTEGER NOT NULL,
        input_tokens   INTEGER NOT NULL DEFAULT 0,
        output_tokens  INTEGER NOT NULL DEFAULT 0,
        llm_calls      INTEGER NOT NULL DEFAULT 0,
        retrieved      TEXT NOT NULL DEFAULT '[]',
        tool_calls     TEXT NOT NULL DEFAULT '[]',
        error          TEXT
    );
    CREATE INDEX idx_requests_created ON requests (created_at);
    CREATE TABLE feedback (
        request_id  TEXT NOT NULL REFERENCES requests (id) ON DELETE CASCADE,
        user_hash   TEXT NOT NULL,
        rating      TEXT NOT NULL CHECK (rating IN ('up', 'down')),
        created_at  REAL NOT NULL,
        PRIMARY KEY (request_id, user_hash)
    );
    CREATE TABLE processed_events (
        key         TEXT PRIMARY KEY,
        created_at  REAL NOT NULL
    );
    CREATE INDEX idx_processed_created ON processed_events (created_at);
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
class RequestRecord:
    id: str
    user_hash: str
    channel_id: str
    outcome: str
    latency_ms: int
    lang: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0
    retrieved: list[dict[str, Any]] | None = None
    tool_calls: list[dict[str, Any]] | None = None
    error: str | None = None


@dataclass(frozen=True)
class RequestStats:
    requests: int
    errors: int
    avg_latency_ms: float | None


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

    # -- event de-duplication -------------------------------------------------------

    def claim_event(self, keys: list[str]) -> bool:
        """Record that an event was seen. Returns False if any key was already processed.

        Use several keys per message (Slack ``event_id`` and ``channel:ts``) so retries and
        the app_mention + message.im pair for the same message are handled once.
        """
        keys = [k for k in keys if k]
        if not keys:
            return True
        with self.transaction() as conn:
            placeholders = ",".join("?" for _ in keys)
            seen = conn.execute(
                f"SELECT 1 FROM processed_events WHERE key IN ({placeholders}) LIMIT 1", keys
            ).fetchone()
            if seen:
                return False
            now = self.clock()
            conn.executemany(
                "INSERT INTO processed_events (key, created_at) VALUES (?, ?)",
                [(k, now) for k in keys],
            )
        return True

    # -- requests and feedback --------------------------------------------------------

    def record_request(self, record: RequestRecord) -> None:
        with self.transaction() as conn:
            conn.execute(
                "INSERT INTO requests (id, created_at, user_hash, channel_id, lang, outcome, model,"
                " latency_ms, input_tokens, output_tokens, llm_calls, retrieved, tool_calls, error)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.id,
                    self.clock(),
                    record.user_hash,
                    record.channel_id,
                    record.lang,
                    record.outcome,
                    record.model,
                    record.latency_ms,
                    record.input_tokens,
                    record.output_tokens,
                    record.llm_calls,
                    json.dumps(record.retrieved or []),
                    json.dumps(record.tool_calls or []),
                    record.error,
                ),
            )

    def request_stats(self, since_seconds: float = 24 * 3600) -> RequestStats:
        row = self.query(
            "SELECT COUNT(*) AS n, SUM(CASE WHEN outcome = 'error' THEN 1 ELSE 0 END) AS errors,"
            " AVG(latency_ms) AS avg_latency FROM requests WHERE created_at >= ?",
            (self.clock() - since_seconds,),
        )[0]
        return RequestStats(
            requests=int(row["n"] or 0),
            errors=int(row["errors"] or 0),
            avg_latency_ms=float(row["avg_latency"]) if row["avg_latency"] is not None else None,
        )

    def record_feedback(self, request_id: str, user_hash: str, rating: str) -> bool:
        """Store (or change) a user's rating of an answer. Returns False for unknown requests."""
        with self.transaction() as conn:
            if not conn.execute("SELECT 1 FROM requests WHERE id = ?", (request_id,)).fetchone():
                return False
            conn.execute(
                "INSERT INTO feedback (request_id, user_hash, rating, created_at)"
                " VALUES (?, ?, ?, ?) ON CONFLICT (request_id, user_hash)"
                " DO UPDATE SET rating = excluded.rating, created_at = excluded.created_at",
                (request_id, user_hash, rating, self.clock()),
            )
        return True

    # -- maintenance ----------------------------------------------------------------

    def cleanup_expired(
        self,
        keep_resolved_seconds: float = 7 * 24 * 3600,
        keep_events_seconds: float = 24 * 3600,
    ) -> dict[str, int]:
        """Delete expired pending actions, old resolved ones and old processed events."""
        now = self.clock()
        with self.transaction() as conn:
            pending = conn.execute(
                "DELETE FROM pending_actions WHERE (status = 'pending' AND expires_at <= ?)"
                " OR (status != 'pending' AND created_at <= ?)",
                (now, now - keep_resolved_seconds),
            ).rowcount
            events = conn.execute(
                "DELETE FROM processed_events WHERE created_at <= ?", (now - keep_events_seconds,)
            ).rowcount
        return {"pending_actions": pending, "processed_events": events}


def _row_to_pending(row: sqlite3.Row) -> PendingAction:
    data = dict(row)
    data["payload"] = json.loads(data["payload"])
    return PendingAction(**data)
