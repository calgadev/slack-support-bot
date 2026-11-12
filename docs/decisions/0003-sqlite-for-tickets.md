# ADR 0003: Store tickets, pending actions and metrics in SQLite

- Status: Accepted
- Date: 2026-11-12

## Context

The bot needs durable state for:

- tickets created after human confirmation;
- pending actions (ticket drafts waiting for Confirm or Cancel), which have an expiry;
- per-request metrics for the `status` command and the evals;
- feedback (thumbs up / down) linked to request ids;
- processed Slack event keys for de-duplication.

The volume is small, there is one writer process, and the project should run with `docker compose up` and no extra services. A real ticketing system (for example GitHub Issues or a service desk tool) is on the roadmap but out of scope for v0.1.

## Decision

Use SQLite through the standard library `sqlite3` module, in a single file under `DATA_DIR` on the Docker volume.

- The schema is defined in one place (`storage/db.py`) as an ordered list of migrations tracked in a `schema_version` table.
- WAL mode is on, and one connection is shared by the Bolt worker threads behind a lock.
- Confirming a ticket draft and inserting the ticket happen in one `BEGIN IMMEDIATE` transaction, so a double click or a retried interaction cannot create duplicates.
- Expired pending actions and old processed-event keys are purged periodically.

## Consequences

- No database server, backups are file copies, and tests use `:memory:` databases.
- Writes are serialized, which is fine at this scale but not suitable for many replicas.
- Tickets are not visible to a real service desk. A future `TicketBackend` (for example GitHub Issues) can keep SQLite for pending actions and metrics while sending confirmed tickets elsewhere.
