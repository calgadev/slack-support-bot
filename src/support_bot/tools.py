"""Tool declarations exposed to Gemini and their validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from google.genai import types

PRIORITIES = ("low", "medium", "high", "critical")
MAX_TITLE = 120
MAX_DESCRIPTION = 2000
MAX_QUERY = 300

SEARCH_DOCS = types.FunctionDeclaration(
    name="search_docs",
    description=(
        "Search the Acme IT knowledge base. Returns numbered document sections with relevance "
        "scores. Use it before answering any question. Write the query in English."
    ),
    parameters_json_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Short search query in English."}
        },
        "required": ["query"],
    },
)

CREATE_TICKET = types.FunctionDeclaration(
    name="create_ticket",
    description=(
        "Draft a support ticket for the Service Desk. Use it only when the user explicitly asks "
        "to open a ticket or report a problem. The user must confirm the draft before it is "
        "created, so never claim the ticket already exists."
    ),
    parameters_json_schema={
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "Short title naming system and problem."},
            "description": {
                "type": "string",
                "description": "What happened, error messages, impact. Never include passwords.",
            },
            "priority": {
                "type": "string",
                "enum": list(PRIORITIES),
                "description": "critical=SEV1, high=SEV2, medium=SEV3, low=SEV4.",
            },
        },
        "required": ["title", "description", "priority"],
    },
)

TOOLS = [types.Tool(function_declarations=[SEARCH_DOCS, CREATE_TICKET])]


class ToolArgumentError(ValueError):
    pass


@dataclass(frozen=True)
class TicketDraft:
    title: str
    description: str
    priority: str

    def to_payload(self) -> dict[str, str]:
        return {"title": self.title, "description": self.description, "priority": self.priority}


def _clean(value: Any, limit: int, *, single_line: bool = True) -> str:
    text = str(value or "")
    text = " ".join(text.split()) if single_line else text.strip()
    return text[:limit]


def parse_search_args(args: dict[str, Any]) -> str:
    query = _clean(args.get("query"), MAX_QUERY)
    if not query:
        raise ToolArgumentError("query must be a non-empty string")
    return query


def parse_ticket_args(args: dict[str, Any]) -> TicketDraft:
    title = _clean(args.get("title"), MAX_TITLE)
    description = _clean(args.get("description"), MAX_DESCRIPTION, single_line=False)
    priority = str(args.get("priority") or "medium").lower().strip()
    if not title:
        raise ToolArgumentError("title must be a non-empty string")
    if priority not in PRIORITIES:
        priority = "medium"
    return TicketDraft(title=title, description=description or title, priority=priority)
