"""Slack event handling, independent from Bolt so it can be unit-tested with fakes."""

from __future__ import annotations

import re
from typing import Any, Protocol

from support_bot.config import Settings
from support_bot.i18n import detect_language, t
from support_bot.llm.client import LLMError
from support_bot.logging_setup import get_logger
from support_bot.orchestrator import Orchestrator

log = get_logger(__name__)

_MENTION = re.compile(r"<@[A-Z0-9]+(\|[^>]*)?>")


class SlackClient(Protocol):
    def chat_postMessage(self, **kwargs: Any) -> Any: ...


def clean_text(text: str) -> str:
    """Remove user mentions and surrounding whitespace."""
    return _MENTION.sub("", text or "").strip()


def should_ignore(event: dict[str, Any], bot_user_id: str | None) -> bool:
    """Skip bot messages (including our own), edits, joins and other subtypes."""
    if event.get("bot_id") or event.get("subtype"):
        return True
    return bool(bot_user_id and event.get("user") == bot_user_id)


class MessageHandler:
    def __init__(self, orchestrator: Orchestrator, settings: Settings) -> None:
        self.orchestrator = orchestrator
        self.settings = settings

    def handle(self, event: dict[str, Any], client: SlackClient, bot_user_id: str | None) -> None:
        if should_ignore(event, bot_user_id):
            return
        channel = event["channel"]
        thread_ts = event.get("thread_ts") or event["ts"]
        text = clean_text(event.get("text", ""))
        lang = detect_language(text)

        def post(message: str) -> None:
            client.chat_postMessage(channel=channel, thread_ts=thread_ts, text=message)

        if not text:
            post(t("empty", lang))
            return
        if len(text) > self.settings.max_input_chars:
            post(t("too_long", lang, length=len(text), limit=self.settings.max_input_chars))
            return
        try:
            answer = self.orchestrator.answer(text)
        except LLMError as exc:
            log.error("llm_failed", error=str(exc), status=exc.status)
            post(t("llm_error", lang))
            return
        except Exception:
            log.exception("handler_failed")
            post(t("internal_error", lang))
            return
        post(answer.text or t("internal_error", lang))
