"""Builds the Slack Bolt app and runs it in Socket Mode."""

from __future__ import annotations

import signal
import sys
import threading
from typing import Any

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from support_bot.config import Settings, get_settings
from support_bot.health import write_heartbeat
from support_bot.logging_setup import configure_logging, get_logger

log = get_logger(__name__)


def build_app(settings: Settings) -> App:
    if settings.slack_bot_token is None:
        raise RuntimeError("SLACK_BOT_TOKEN is not set")
    app = App(token=settings.slack_bot_token.get_secret_value())

    def reply(event: dict[str, Any], say: Any) -> None:
        say(text="hello", thread_ts=event.get("thread_ts") or event["ts"])

    @app.event("app_mention")
    def on_mention(event: dict[str, Any], say: Any) -> None:
        reply(event, say)

    @app.event("message")
    def on_message(event: dict[str, Any], say: Any) -> None:
        if event.get("channel_type") != "im" or event.get("bot_id") or event.get("subtype"):
            return
        reply(event, say)

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
