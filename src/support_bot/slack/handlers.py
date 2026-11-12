"""Slack event and action handling, independent from Bolt so it can be unit-tested with fakes."""

from __future__ import annotations

import re
import time
import uuid
from collections.abc import Callable
from typing import Any, Protocol

import structlog

from support_bot.config import Settings
from support_bot.i18n import Lang, detect_language, t
from support_bot.llm.client import LLMError
from support_bot.logging_setup import get_logger
from support_bot.observability import build_request_record, hash_user_id
from support_bot.orchestrator import Answer, Orchestrator
from support_bot.slack.blocks import (
    ACTION_FEEDBACK_UP,
    ACTION_TICKET_CONFIRM,
    escape,
    feedback_blocks,
    section,
    text_sections,
    ticket_confirmation_blocks,
)
from support_bot.status import StatusService, is_status_request
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
    if event.get("bot_id") or event.get("subtype") or not event.get("user"):
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


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


class MessageHandler:
    def __init__(
        self,
        orchestrator: Orchestrator,
        db: Database,
        settings: Settings,
        status: StatusService,
        request_id_factory: Callable[[], str] = new_request_id,
    ) -> None:
        self.orchestrator = orchestrator
        self.db = db
        self.settings = settings
        self.status = status
        self.new_request_id = request_id_factory
        self._salt = settings.user_id_hash_salt.get_secret_value()

    def handle(
        self,
        event: dict[str, Any],
        client: SlackClient,
        bot_user_id: str | None,
        event_id: str | None = None,
    ) -> None:
        if should_ignore(event, bot_user_id):
            return
        channel = event["channel"]
        # The same message can arrive as app_mention and message.im, and Slack retries
        # deliveries; both keys must be new for the message to be processed.
        keys = [f"msg:{channel}:{event['ts']}"]
        if event_id:
            keys.append(f"event:{event_id}")
        if not self.db.claim_event(keys):
            log.info("duplicate_event_skipped", event_id=event_id, channel=channel)
            return

        request_id = self.new_request_id()
        with structlog.contextvars.bound_contextvars(request_id=request_id):
            self._process(event, client, request_id)

    def _process(self, event: dict[str, Any], client: SlackClient, request_id: str) -> None:
        channel = event["channel"]
        user_hash = hash_user_id(event["user"], self._salt)
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
        if is_status_request(text):
            post(self.status.render(lang))
            log.info("status_requested", user_hash=user_hash)
            return

        started = time.perf_counter()
        outcome, answer, error = "error", None, None
        try:
            if len(text) > self.settings.max_input_chars:
                outcome = "rejected_too_long"
                post(t("too_long", lang, length=len(text), limit=self.settings.max_input_chars))
                return
            try:
                answer = self.orchestrator.answer(text)
            except LLMError as exc:
                error = f"LLMError: {exc} (status={exc.status})"
                if exc.quota_exhausted:
                    outcome = "quota_exhausted"
                    log.error("llm_quota_exhausted", retry_after=exc.retry_after)
                # Ticket drafts need no LLM, so the user can still reach the Service Desk.
                intro = t("quota_exhausted" if exc.quota_exhausted else "llm_error", lang)
                self._offer_ticket(draft_from_question(text), intro, event, request_id, lang, post)
                return
            outcome = answer.outcome
            self._reply(answer, text, event, request_id, lang, post)
        except Exception as exc:
            outcome, error = "error", f"{type(exc).__name__}: {exc}"[:500]
            log.exception("handler_failed")
            try:
                post(t("internal_error", lang))
            except Exception:
                log.exception("error_reply_failed")
        finally:
            latency_ms = int((time.perf_counter() - started) * 1000)
            record = build_request_record(
                request_id=request_id,
                user_hash=user_hash,
                channel_id=channel,
                lang=lang,
                latency_ms=latency_ms,
                outcome=outcome,
                answer=answer,
                error=error,
            )
            log.info(
                "request_completed",
                user_hash=user_hash,
                outcome=outcome,
                latency_ms=latency_ms,
                model=record.model,
                input_tokens=record.input_tokens,
                output_tokens=record.output_tokens,
                llm_calls=record.llm_calls,
                retrieved=record.retrieved,
                tool_calls=record.tool_calls,
                error=error,
                input_chars=len(text),
            )
            try:
                self.db.record_request(record)
            except Exception:
                log.exception("record_request_failed")

    def _reply(
        self,
        answer: Answer,
        question: str,
        event: dict[str, Any],
        request_id: str,
        lang: Lang,
        post: Callable[..., None],
    ) -> None:
        feedback = feedback_blocks(request_id, lang)
        if answer.outcome == "answered":
            text = format_answer(answer, lang)
            post(text, [*text_sections(text), *feedback])
            return

        # Low confidence or an explicit ticket request: show a draft that needs confirmation.
        if answer.outcome == "ticket_proposed" and answer.ticket is not None:
            draft, intro = answer.ticket, t("ticket_draft", lang)
            feedback = []  # nothing to rate yet
        else:
            draft, intro = draft_from_question(question), t("low_confidence", lang)
        self._offer_ticket(draft, intro, event, request_id, lang, post, feedback)

    def _offer_ticket(
        self,
        draft: TicketDraft,
        intro: str,
        event: dict[str, Any],
        request_id: str,
        lang: Lang,
        post: Callable[..., None],
        extra_blocks: list[dict[str, Any]] | None = None,
    ) -> None:
        """Post a ticket draft with Confirm / Cancel buttons (stored as a pending action)."""
        pending = self.db.create_pending_action(
            action="create_ticket",
            payload={**draft.to_payload(), "lang": lang},
            user_id=event["user"],
            channel_id=event["channel"],
            thread_ts=event.get("thread_ts") or event["ts"],
            request_id=request_id,
            ttl_seconds=self.settings.pending_action_ttl_seconds,
        )
        blocks = ticket_confirmation_blocks(intro, draft, pending.id, lang)
        post(intro, [*blocks, *(extra_blocks or [])])


class ActionHandler:
    """Handles Block Kit buttons: ticket Confirm / Cancel and answer feedback."""

    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self._salt = settings.user_id_hash_salt.get_secret_value()

    def handle_feedback(self, body: dict[str, Any], client: SlackClient) -> None:
        action = body["actions"][0]
        request_id = action.get("value", "")
        user_id = body["user"]["id"]
        rating = "up" if action["action_id"] == ACTION_FEEDBACK_UP else "down"
        stored = self.db.record_feedback(request_id, hash_user_id(user_id, self._salt), rating)
        log.info("feedback_received", request_id=request_id, rating=rating, stored=stored)
        rows = self.db.query("SELECT lang FROM requests WHERE id = ?", (request_id,))
        lang: Lang = (rows[0]["lang"] if rows else None) or "en"
        client.chat_postEphemeral(
            channel=body["channel"]["id"],
            user=user_id,
            thread_ts=body["message"].get("thread_ts"),
            text=t("feedback_thanks", lang),
        )

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
                log.info(
                    "ticket_created",
                    ticket=ticket.key,
                    priority=ticket.priority,
                    request_id=pending.request_id,
                )
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
