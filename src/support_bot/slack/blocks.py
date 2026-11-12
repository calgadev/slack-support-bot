"""Block Kit builders."""

from __future__ import annotations

from typing import Any

from support_bot.i18n import Lang, t
from support_bot.tools import TicketDraft

Block = dict[str, Any]

ACTION_TICKET_CONFIRM = "ticket_confirm"
ACTION_TICKET_CANCEL = "ticket_cancel"

_SECTION_LIMIT = 3000  # Slack limit for a section's text


def escape(text: str) -> str:
    """Escape user/LLM-provided text so it cannot inject mentions like <!channel>."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def section(text: str) -> Block:
    if len(text) > _SECTION_LIMIT:
        text = text[: _SECTION_LIMIT - 1] + "…"
    return {"type": "section", "text": {"type": "mrkdwn", "text": text}}


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
