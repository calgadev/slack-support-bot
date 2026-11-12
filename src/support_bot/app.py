"""Builds the Slack Bolt app and runs it in Socket Mode."""

from __future__ import annotations

import signal
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any

from slack_bolt import App, BoltContext
from slack_bolt.adapter.socket_mode import SocketModeHandler

from support_bot.config import Settings, get_settings
from support_bot.health import write_heartbeat
from support_bot.llm.client import GeminiClient
from support_bot.logging_setup import configure_logging, get_logger
from support_bot.orchestrator import Orchestrator
from support_bot.rag.store import Retriever, VectorStore
from support_bot.slack.blocks import (
    ACTION_FEEDBACK_DOWN,
    ACTION_FEEDBACK_UP,
    ACTION_TICKET_CANCEL,
    ACTION_TICKET_CONFIRM,
)
from support_bot.slack.handlers import ActionHandler, MessageHandler
from support_bot.status import StatusService
from support_bot.storage.db import Database

log = get_logger(__name__)


def build_llm(settings: Settings) -> GeminiClient:
    if settings.gemini_api_key is None:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return GeminiClient(
        api_key=settings.gemini_api_key.get_secret_value(),
        model=settings.gemini_model,
        embedding_model=settings.gemini_embedding_model,
        embedding_dim=settings.gemini_embedding_dim,
        timeout_seconds=settings.gemini_timeout_seconds,
        max_attempts=settings.gemini_max_attempts,
        max_output_tokens=settings.gemini_max_output_tokens,
    )


@dataclass
class BotComponents:
    app: App
    db: Database


def build_app(settings: Settings, *, verify_token: bool = True) -> BotComponents:
    if settings.slack_bot_token is None:
        raise RuntimeError("SLACK_BOT_TOKEN is not set")
    app = App(
        token=settings.slack_bot_token.get_secret_value(),
        token_verification_enabled=verify_token,
    )
    llm = build_llm(settings)
    store = VectorStore(
        settings.chroma_dir, settings.gemini_embedding_model, settings.gemini_embedding_dim
    )
    store.check_compatible()
    if store.count() == 0:
        log.warning("knowledge_base_empty", hint="run `uv run support-bot-ingest`")
    db = Database(settings.sqlite_path)
    retriever = Retriever(store, llm, settings.retrieval_top_k)
    orchestrator = Orchestrator(llm, retriever, settings.retrieval_min_score)
    status = StatusService(db, store.count, started_at=time.time())
    messages = MessageHandler(orchestrator, db, settings, status)
    actions = ActionHandler(db, settings)

    @app.event("app_mention")
    def on_mention(
        event: dict[str, Any], body: dict[str, Any], client: Any, context: BoltContext
    ) -> None:
        messages.handle(event, client, context.bot_user_id, body.get("event_id"))

    @app.event("message")
    def on_message(
        event: dict[str, Any], body: dict[str, Any], client: Any, context: BoltContext
    ) -> None:
        if event.get("channel_type") != "im":
            return
        messages.handle(event, client, context.bot_user_id, body.get("event_id"))

    @app.action(ACTION_FEEDBACK_UP)
    @app.action(ACTION_FEEDBACK_DOWN)
    def on_feedback(ack: Any, body: dict[str, Any], client: Any) -> None:
        ack()
        actions.handle_feedback(body, client)

    @app.action(ACTION_TICKET_CONFIRM)
    @app.action(ACTION_TICKET_CANCEL)
    def on_ticket_action(ack: Any, body: dict[str, Any], client: Any) -> None:
        ack()
        actions.handle_ticket_action(body, client)

    return BotComponents(app=app, db=db)


def run(settings: Settings) -> None:
    if settings.slack_app_token is None:
        raise RuntimeError("SLACK_APP_TOKEN is not set")
    if settings.user_id_hash_salt.get_secret_value() == "change-me":
        log.warning("default_user_id_hash_salt", hint="set USER_ID_HASH_SALT")
    components = build_app(settings)
    handler = SocketModeHandler(components.app, settings.slack_app_token.get_secret_value())
    stop = threading.Event()

    def _shutdown(signum: int, _frame: Any) -> None:
        log.info("shutdown_requested", signal=signum)
        stop.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    handler.connect()
    log.info("socket_mode_connected")
    last_cleanup = 0.0
    try:
        while not stop.is_set():
            if handler.client.is_connected():
                write_heartbeat(settings.heartbeat_path)
            else:
                log.warning("socket_mode_disconnected")
            if time.monotonic() - last_cleanup >= settings.cleanup_interval_seconds:
                try:
                    removed = components.db.cleanup_expired(
                        keep_events_seconds=settings.processed_event_ttl_seconds
                    )
                    log.info("cleanup_done", **removed)
                except Exception:
                    log.exception("cleanup_failed")
                last_cleanup = time.monotonic()
            stop.wait(settings.heartbeat_interval_seconds)
    finally:
        handler.close()
        components.db.close()
        log.info("stopped")


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    try:
        run(settings)
    except RuntimeError as exc:  # includes EmbeddingConfigMismatch
        log.error("startup_failed", error=str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
