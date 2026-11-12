"""Block Kit builders."""

from __future__ import annotations

from typing import Any

from support_bot.i18n import Lang, t
from support_bot.tools import TicketDraft

Block = dict[str, Any]

ACTION_TICKET_CONFIRM = "ticket_confirm"
ACTION_TICKET_CANCEL = "ticket_cancel"
ACTION_FEEDBACK_UP = "feedback_up"
ACTION_FEEDBACK_DOWN = "feedback_down"

_SECTION_LIMIT = 3000  # Slack limit for a section's text


def escape(text: str) -> str:
    """Escape user/LLM-provided text so it cannot inject mentions like <!channel>."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def section(text: str) -> Block:
    if len(text) > _SECTION_LIMIT:
        text = text[: _SECTION_LIMIT - 1] + "…"
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


def text_sections(text: str) -> list[Block]:
    """Split long text into several sections, breaking on line boundaries."""
    blocks: list[Block] = []
    current = ""
    for line in text.split("\n"):
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > _SECTION_LIMIT and current:
            blocks.append(section(current))
            current = line
        else:
            current = candidate
    if current:
        blocks.append(section(current))
    return blocks


def feedback_blocks(request_id: str, lang: Lang) -> list[Block]:
    return [
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": t("feedback_prompt", lang)}],
        },
        {
            "type": "actions",
            "block_id": "feedback",
            "elements": [
                {
                    "type": "button",
                    "action_id": ACTION_FEEDBACK_UP,
                    "text": {"type": "plain_text", "text": ":+1:", "emoji": True},
                    "value": request_id,
                },
                {
                    "type": "button",
                    "action_id": ACTION_FEEDBACK_DOWN,
                    "text": {"type": "plain_text", "text": ":-1:", "emoji": True},
                    "value": request_id,
                },
            ],
        },
    ]


def ticket_confirmation_blocks(
    intro: str, draft: TicketDraft, pending_id: str, lang: Lang
) -> list[Block]:
    description = draft.description
    if len(description) > 500:
        description = description[:500] + "…"
    fields = t(
        "ticket_fields",
        lang,
        title=escape(draft.title),
        priority=draft.priority,
        description=escape(description),
    )
    return [
        section(intro),
        section(fields),
        {
            "type": "actions",
            "block_id": "ticket_confirmation",
            "elements": [
                {
                    "type": "button",
                    "action_id": ACTION_TICKET_CONFIRM,
                    "style": "primary",
                    "text": {"type": "plain_text", "text": t("btn_confirm", lang)},
                    "value": pending_id,
                },
                {
                    "type": "button",
                    "action_id": ACTION_TICKET_CANCEL,
                    "text": {"type": "plain_text", "text": t("btn_cancel", lang)},
                    "value": pending_id,
                },
            ],
        },
    ]
