"""Slack event and action handling, independent from Bolt so it can be unit-tested with fakes."""

from __future__ import annotations

import re
from typing import Any, Protocol

from support_bot.config import Settings
from support_bot.i18n import Lang, detect_language, t
from support_bot.llm.client import LLMError
from support_bot.logging_setup import get_logger
from support_bot.orchestrator import Answer, Orchestrator
from support_bot.slack.blocks import (
    ACTION_TICKET_CONFIRM,
    escape,
    section,
    ticket_confirmation_blocks,
)
from support_bot.storage.db import Database
from support_bot.tools import MAX_TITLE, TicketDraft

log = get_logger(__name__)

_MENTION = re.compile(r"<@[A-Z0-9]+(\|[^>]*)?>")


class SlackClient(Protocol):
    def chat_postMessage(self, **kwargs: Any) -> Any: ...

    def chat_postEphemeral(self, **kwargs: Any) -> Any: ...

    def chat_update(self, **kwargs: Any) -> Any: ...


def clean_text(text: str) -> str:
    """Remove user mentions and surrounding whitespace."""
    return _MENTION.sub("", text or "").strip()


def should_ignore(event: dict[str, Any], bot_user_id: str | None) -> bool:
    """Skip bot messages (including our own), edits, joins and other subtypes."""
    if event.get("bot_id") or event.get("subtype"):
        return True
    return bool(bot_user_id and event.get("user") == bot_user_id)


def format_answer(answer: Answer, lang: Lang) -> str:
    sources = "\n".join(
        f"[{n}] {chunk.citation}" for n, chunk in enumerate(answer.citations, start=1)
    )
    return f"{answer.text}\n\n*{t('sources', lang)}:*\n{sources}"


def draft_from_question(question: str) -> TicketDraft:
    title = " ".join(question.split())
    if len(title) > 80:
        title = title[:79] + "…"
    return TicketDraft(title=title[:MAX_TITLE], description=question, priority="medium")


class MessageHandler:
    def __init__(self, orchestrator: Orchestrator, db: Database, settings: Settings) -> None:
        self.orchestrator = orchestrator
        self.db = db
        self.settings = settings

    def handle(self, event: dict[str, Any], client: SlackClient, bot_user_id: str | None) -> None:
        if should_ignore(event, bot_user_id):
            return
        channel = event["channel"]
        user_id = event.get("user", "")
        thread_ts = event.get("thread_ts") or event["ts"]
        text = clean_text(event.get("text", ""))
        lang = detect_language(text)

        def post(message: str, blocks: list[dict[str, Any]] | None = None) -> None:
            kwargs: dict[str, Any] = {"channel": channel, "thread_ts": thread_ts, "text": message}
            if blocks:
                kwargs["blocks"] = blocks
            client.chat_postMessage(**kwargs)

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

        if answer.outcome == "answered":
            post(format_answer(answer, lang))
            return

        # Low confidence or an explicit ticket request: show a draft that needs confirmation.
        if answer.outcome == "ticket_proposed" and answer.ticket is not None:
            draft, intro = answer.ticket, t("ticket_draft", lang)
        else:
            draft, intro = draft_from_question(text), t("low_confidence", lang)
        pending = self.db.create_pending_action(
            action="create_ticket",
            payload={**draft.to_payload(), "lang": lang},
            user_id=user_id,
            channel_id=channel,
            thread_ts=thread_ts,
            request_id=None,
            ttl_seconds=self.settings.pending_action_ttl_seconds,
        )
        post(intro, ticket_confirmation_blocks(intro, draft, pending.id, lang))


class ActionHandler:
    """Handles the Confirm / Cancel buttons of ticket drafts."""

    def __init__(self, db: Database) -> None:
        self.db = db

    def handle_ticket_action(self, body: dict[str, Any], client: SlackClient) -> None:
        action = body["actions"][0]
        pending_id = action.get("value", "")
        user_id = body["user"]["id"]
        channel = body["channel"]["id"]
        message_ts = body["message"]["ts"]

        pending = self.db.get_pending_action(pending_id)
        lang: Lang = (pending.payload.get("lang") if pending else None) or "en"
        if pending is None:
            self._replace(client, channel, message_ts, t("ticket_not_found", lang))
            return
        if user_id != pending.user_id:
            client.chat_postEphemeral(
                channel=channel,
                user=user_id,
                thread_ts=pending.thread_ts,
                text=t("ticket_not_owner", lang),
            )
            return

        if action["action_id"] == ACTION_TICKET_CONFIRM:
            _, status, ticket = self.db.confirm_ticket_action(pending_id)
            if status == "ok" and ticket is not None:
                log.info("ticket_created", ticket=ticket.key, priority=ticket.priority)
                message = t(
                    "ticket_created",
                    lang,
                    key=ticket.key,
                    title=escape(ticket.title),
                    priority=ticket.priority,
                )
                self._replace(client, channel, message_ts, message)
                return
        else:
            _, status = self.db.cancel_pending_action(pending_id)
            if status == "ok":
                self._replace(client, channel, message_ts, t("ticket_cancelled", lang))
                return

        key = {"expired": "ticket_expired", "already_resolved": "ticket_already"}.get(
            status, "ticket_not_found"
        )
        self._replace(client, channel, message_ts, t(key, lang))

    @staticmethod
    def _replace(client: SlackClient, channel: str, ts: str, text: str) -> None:
        """Replace the draft message so its buttons cannot be clicked again."""
        client.chat_update(channel=channel, ts=ts, text=text, blocks=[section(text)])
