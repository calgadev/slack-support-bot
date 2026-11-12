"""Builds the Slack Bolt app and runs it in Socket Mode."""

from __future__ import annotations

import signal
import sys
import threading
from typing import Any

from slack_bolt import App, BoltContext
from slack_bolt.adapter.socket_mode import SocketModeHandler

from support_bot.config import Settings, get_settings
from support_bot.health import write_heartbeat
from support_bot.llm.client import GeminiClient
from support_bot.logging_setup import configure_logging, get_logger
from support_bot.orchestrator import Orchestrator
from support_bot.slack.handlers import MessageHandler

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


def build_app(settings: Settings) -> App:
    if settings.slack_bot_token is None:
        raise RuntimeError("SLACK_BOT_TOKEN is not set")
    app = App(token=settings.slack_bot_token.get_secret_value())
    handler = MessageHandler(Orchestrator(build_llm(settings)), settings)

    @app.event("app_mention")
    def on_mention(event: dict[str, Any], client: Any, context: BoltContext) -> None:
        handler.handle(event, client, context.bot_user_id)

    @app.event("message")
    def on_message(event: dict[str, Any], client: Any, context: BoltContext) -> None:
        if event.get("channel_type") != "im":
            return
        handler.handle(event, client, context.bot_user_id)

    return app


def run(settings: Settings) -> None:
    if settings.slack_app_token is None:
        raise RuntimeError("SLACK_APP_TOKEN is not set")
    app = build_app(settings)
    handler = SocketModeHandler(app, settings.slack_app_token.get_secret_value())
    stop = threading.Event()

    def _shutdown(signum: int, _frame: Any) -> None:
        log.info("shutdown_requested", signal=signum)
        stop.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    handler.connect()
    log.info("socket_mode_connected")
    try:
        while not stop.is_set():
            if handler.client.is_connected():
                write_heartbeat(settings.heartbeat_path)
            else:
                log.warning("socket_mode_disconnected")
            stop.wait(settings.heartbeat_interval_seconds)
    finally:
        handler.close()
        log.info("stopped")


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    try:
        run(settings)
    except RuntimeError as exc:
        log.error("startup_failed", error=str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
